import datetime

from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DAYS_AHEAD, N_SLOTS, Project, Reservation, Slot

from .calendar import Availability, can_book  # noqa: E402

TEST_PASSWORD = 'test-pass'


def state(project, slot, now=None):
    return Availability(project, slot.start, slot.start + datetime.timedelta(minutes=30), now).admin_state(slot.start)
TEST_HASH = make_password(TEST_PASSWORD)


def login(client):
    client.post(reverse('setting_login'), {'password': TEST_PASSWORD})


def tomorrow_slot(project, hour=10):
    day = datetime.date.today() + datetime.timedelta(days=1)
    return Slot.objects.get(project=project, start=datetime.datetime.combine(day, datetime.time(hour)))


class CloseCutoffTests(TestCase):
    def test_cutoff_modes(self):
        p = Project(name='c')
        now = datetime.datetime(2026, 11, 6, 10, 15)
        midnight = datetime.datetime(2026, 11, 7)
        cases = [
            (('hours', 2), datetime.datetime(2026, 11, 6, 12, 15)),
            (('hours', 24), datetime.datetime(2026, 11, 7, 10, 15)),
            (('today', 0), midnight),
            (('tomorrow', 0), midnight + datetime.timedelta(days=1)),
            (('days', 1), midnight + datetime.timedelta(days=1)),
            (('days', 7), midnight + datetime.timedelta(days=7)),
        ]
        for (mode, value), expected in cases:
            p.close_mode, p.close_value = mode, value
            self.assertEqual(p.close_cutoff(now), expected, (mode, value))

    def test_same_day_booking(self):
        project = Project.objects.create(name='same')
        project.ensure_slots()
        # 明日の10:00を「今」として、当日の枠が締め切りに合わせて予約できるかを確かめる
        day = datetime.date.today() + datetime.timedelta(days=1)
        now = datetime.datetime.combine(day, datetime.time(10))
        soon = tomorrow_slot(project, 11)    # 1時間後
        later = tomorrow_slot(project, 14)   # 4時間後
        self.assertFalse(can_book(project, soon, now))
        self.assertEqual(state(project, soon, now), 'none')
        self.assertTrue(can_book(project, later, now))  # 当日でも締め切り（2時間前）より後なら予約できる
        self.assertEqual(state(project, later, now), 'open')
        for mode, value, expected in [('hours', 5, False), ('today', 0, False), ('hours', 1, True)]:
            project.close_mode, project.close_value = mode, value
            self.assertEqual(can_book(project, later, now), expected, (mode, value))


class DurationBufferTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name='dur', duration=60)
        self.project.ensure_slots()

    def slot(self, hour, minute=0):
        day = datetime.date.today() + datetime.timedelta(days=1)
        return Slot.objects.get(project=self.project, start=datetime.datetime.combine(day, datetime.time(hour, minute)))

    def book(self, hour, minute=0):
        return Reservation.objects.create(slot=self.slot(hour, minute), duration=self.project.duration)

    def test_duration(self):
        self.book(12)  # 12:00〜13:00
        self.assertFalse(can_book(self.project, self.slot(11, 30)))  # 11:30〜12:30 は重なる
        self.assertTrue(can_book(self.project, self.slot(11)))       # 11:00〜12:00 はちょうど空いている
        self.assertFalse(can_book(self.project, self.slot(12, 30)))  # 予約の途中
        self.assertTrue(can_book(self.project, self.slot(13)))
        self.assertEqual(state(self.project, self.slot(12, 30)), 'reserved')  # 所要時間ぶん「予」
        # 終わりが募集時間（21:00）を越える枠は選べない
        self.assertTrue(can_book(self.project, self.slot(20)))
        self.assertFalse(can_book(self.project, self.slot(20, 30)))
        # 後ろに受付停止の枠があると選べない
        closed = self.slot(16, 30)
        closed.closed = True
        closed.save()
        self.assertFalse(can_book(self.project, self.slot(16)))
        self.assertTrue(can_book(self.project, self.slot(15, 30)))

    def test_buffer_before(self):
        self.project.buffer_enabled = True
        self.project.buffer_side, self.project.buffer_minutes = 'before', 30
        self.project.save()
        self.book(12)
        self.assertEqual(state(self.project, self.slot(11, 30)), 'none')  # 予約の前30分は閉じる
        self.assertEqual(state(self.project, self.slot(13)), 'open')
        self.assertFalse(can_book(self.project, self.slot(11)))      # 11:00〜12:00 は前のバッファ（11:30〜）に重なる
        self.assertTrue(can_book(self.project, self.slot(10, 30)))   # 10:30〜11:30 なら、そのあと30分空く
        # 直後の予約は、その予約の前30分に今の予約がかかるのでできない
        self.assertFalse(can_book(self.project, self.slot(13)))
        self.assertTrue(can_book(self.project, self.slot(13, 30)))

    def test_buffer_both(self):
        self.project.buffer_enabled = True
        self.project.buffer_side, self.project.buffer_minutes = 'both', 60
        self.project.save()
        self.book(12)
        for h, m in [(11, 0), (11, 30), (13, 0), (13, 30)]:
            self.assertEqual(state(self.project, self.slot(h, m)), 'none', (h, m))
        self.assertFalse(can_book(self.project, self.slot(13, 30)))
        self.assertTrue(can_book(self.project, self.slot(14)))       # 予約の終わり（13:00）から1時間空く
        self.assertTrue(can_book(self.project, self.slot(10)))       # 10:00〜11:00、そのあと1時間空く
        self.assertFalse(can_book(self.project, self.slot(10, 30)))

    def test_booking_uses_duration(self):
        slot = self.slot(10)
        self.client.post(reverse('confirm', args=['dur']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        r = Reservation.objects.get(slot=slot)
        self.assertEqual(r.duration, 60)
        self.assertIn('10:00〜11:00', r.label())
        # プロジェクトの所要時間を変えても、入っている予約の時間は変わらない
        self.project.duration = 30
        self.project.save()
        r.refresh_from_db()
        self.assertIn('10:00〜11:00', r.label())
        # 予約の途中から始まる枠には申し込めない
        response = self.client_class().post(reverse('confirm', args=['dur']),
                                            {'slot': self.slot(10, 30).pk, 'full_name': 'y', 'mail': 'b@example.com'})
        self.assertContains(response, '申し訳ございません')

    def test_entry_rechecks_slot(self):
        # 日時選択の画面を開いたあとに、後ろの枠が閉じられたとき
        page = self.client.get(reverse('timeframe', args=['dur']))
        self.assertContains(page, f'value="{self.slot(20).pk}"')
        self.assertEqual(page['Cache-Control'].count('no-store'), 1)
        closed = self.slot(20, 30)
        closed.closed = True
        closed.save()
        response = self.client.post(reverse('entry', args=['dur']), {'slot': self.slot(20).pk})
        self.assertContains(response, 'この日時は予約できなくなりました')
        self.assertNotContains(self.client.get(reverse('timeframe', args=['dur'])), f'value="{self.slot(20).pk}"')

    def test_faint_cells(self):
        # 21:00 を閉じると、20:00 からは予約できるが、20:30 は空いているのに始められないので薄い◯
        closed = self.slot(21)
        self.project.time_end = datetime.time(22)
        self.project.save()
        closed.closed = True
        closed.save()
        from .calendar import user_week
        week = user_week(self.project, datetime.date.today() + datetime.timedelta(days=1))
        rows = {r['time']: r['cells'][0] for r in week['rows']}
        self.assertEqual(rows['20:00']['slot'].pk, self.slot(20).pk)
        self.assertEqual(rows['20:30'], {'faint': True})
        self.assertIsNone(rows['21:00'])
        self.assertTrue(rows['21:30'] is None or rows['21:30'] == {'faint': True})

    def test_user_page_shows_duration(self):
        page = self.client.get(reverse('timeframe', args=['dur']))
        self.assertContains(page, '所要時間：1時間')
        self.assertContains(page, 'data-span="2"')
        self.assertNotContains(page, '予約できません')


class SlotTests(TestCase):
    def test_slots_cover_today_to_90_days(self):
        project = Project.objects.create(name='exp1')
        project.ensure_slots()
        self.assertEqual(Slot.objects.filter(project=project).count(), (DAYS_AHEAD + 1) * N_SLOTS)
        # 日が進むと、足りない日の分だけ作る（すでにある枠は残す）
        later = datetime.date.today() + datetime.timedelta(days=3)
        project.ensure_slots(today=later)
        self.assertEqual(Slot.objects.filter(project=project).count(), (DAYS_AHEAD + 4) * N_SLOTS)
        last = Slot.objects.filter(project=project).order_by('-start').first().start.date()
        self.assertEqual(last, later + datetime.timedelta(days=DAYS_AHEAD))

    def test_project_name_validation(self):
        from django.core.exceptions import ValidationError
        from .models import validate_project_name
        for ok in ['exp1', 'A-b_c.d~!', "x(1)+y=z:@"]:
            validate_project_name(ok)
        for ng in ['実験', 'a b', 'a/b', 'setting', '..', 'a?b', 'a#b', 'a%b']:
            with self.assertRaises(ValidationError, msg=ng):
                validate_project_name(ng)


class ParticipantFlowTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name='exp-1', use_full_name=True, use_mail=True, use_data_reuse=True,
            use_extra4=True, title_extra4='18歳以上ですか',
            complete_text='予約：{日時}', complete_button_enabled=True,
            complete_button_text='アンケートへ', complete_button_url='https://example.com/q',
        )
        self.project.ensure_slots()

    def test_consent_without_manual_enables_next(self):
        response = self.client.get(reverse('consent', args=['exp-1']))
        self.assertContains(response, 'id="next_button"')
        self.assertNotContains(response, 'onclick="enableNext()"')

    def test_consent_with_manual(self):
        self.project.manual_data = b'%PDF-1.4'
        self.project.manual_name = '説明書.pdf'
        self.project.manual_type = 'application/pdf'
        self.project.save()
        response = self.client.get(reverse('consent', args=['exp-1']))
        self.assertContains(response, '説明書を読む')
        self.assertContains(response, 'disabled>次へ進む')
        manual = self.client.get(reverse('manual', args=['exp-1']))
        self.assertEqual(manual['Content-Type'], 'application/pdf')
        self.assertEqual(manual.content, b'%PDF-1.4')

    def test_timeframe_marks(self):
        closed = tomorrow_slot(self.project, 9)
        closed.closed = True
        closed.save()
        Reservation.objects.create(slot=tomorrow_slot(self.project, 11), full_name='予約済')
        response = self.client.get(reverse('timeframe', args=['exp-1']))
        self.assertContains(response, f'value="{tomorrow_slot(self.project, 10).pk}"')
        self.assertNotContains(response, f'value="{closed.pk}"')
        # 参加者には、受付停止も予約ありも「×」と見せる
        self.assertNotContains(response, f'value="{tomorrow_slot(self.project, 11).pk}"')
        self.assertNotContains(response, 'mark--reserved')
        self.assertContains(response, 'mark--closed">×')
        self.assertNotContains(response, '・祝')

    def test_period_limits_user_calendar(self):
        self.project.time_start = datetime.time(10)
        self.project.time_end = datetime.time(12)
        self.project.save()
        response = self.client.get(reverse('timeframe', args=['exp-1']))
        self.assertContains(response, f'value="{tomorrow_slot(self.project, 10).pk}"')
        self.assertNotContains(response, f'value="{tomorrow_slot(self.project, 9).pk}"')
        self.assertNotContains(response, f'value="{tomorrow_slot(self.project, 12).pk}"')
        self.assertContains(response, '<th class="time">11:30</th>')
        self.assertNotContains(response, '<th class="time">12:00</th>')
        # 期間外の枠は申し込めない
        data = {'slot': tomorrow_slot(self.project, 9).pk, 'full_name': 'x', 'mail': 'a@example.com',
                'data_reuse': 'no', 'extra4': 'no'}
        response = self.client.post(reverse('confirm', args=['exp-1']), data)
        self.assertContains(response, '申し訳ございません')

    def test_week_loading(self):
        from .calendar import user_week_starts
        starts = user_week_starts(Project.objects.get(pk=self.project.pk))
        self.assertEqual(starts[0], datetime.date.today())  # 今日が一番左
        self.assertEqual(len(starts), 2)  # 初期値の募集期間（今日から13日後まで＝2週間）
        page = self.client.get(reverse('timeframe', args=['exp-1']))
        self.assertEqual(page.content.decode().count('class="grid-wrap week"'), 1)  # 最初は1週間分だけ
        response = self.client.get(reverse('week', args=['exp-1']) + f'?start={starts[1]}')
        self.assertContains(response, 'class="grid-wrap week"')
        self.assertEqual(self.client.get(reverse('week', args=['exp-1']) + '?start=2000-01-01').status_code, 404)

    def test_header_shows_month_once(self):
        from .calendar import user_week
        project = Project.objects.get(pk=self.project.pk)
        week = user_week(project, datetime.date(2026, 11, 28))
        self.assertEqual(week['month'], '11月')
        self.assertEqual([c['head'] for c in week['columns']], ['28', '29', '30', '12/1', '2', '3', '4'])

    def test_booking(self):
        slot = tomorrow_slot(self.project)
        entry = self.client.post(reverse('entry', args=['exp-1']), {'slot': slot.pk})
        self.assertContains(entry, '氏名')
        self.assertContains(entry, '18歳以上ですか')
        self.assertNotContains(entry, '性別')

        data = {'slot': slot.pk, 'full_name': '山田太郎', 'mail': 'a@example.com', 'data_reuse': 'yes', 'extra4': 'no'}
        response = self.client.post(reverse('confirm', args=['exp-1']), data)
        self.assertRedirects(response, reverse('complete', args=['exp-1']))
        r = Reservation.objects.get(slot=slot)
        self.assertEqual((r.full_name, r.data_reuse, r.extra4, r.status), ('山田太郎', True, False, 'reserved'))

        complete = self.client.get(reverse('complete', args=['exp-1']))
        self.assertContains(complete, '予約：' + slot.label(with_year=True))
        self.assertContains(complete, 'href="https://example.com/q"')

        # 二度押しは同じ予約として完了画面へ
        again = self.client.post(reverse('confirm', args=['exp-1']), data)
        self.assertRedirects(again, reverse('complete', args=['exp-1']))
        self.assertEqual(Reservation.objects.count(), 1)

        # 別の人は同じ枠を予約できない
        other = self.client_class()
        response = other.post(reverse('confirm', args=['exp-1']), {**data, 'mail': 'b@example.com'})
        self.assertContains(response, '申し訳ございません')
        self.assertEqual(Reservation.objects.count(), 1)

    def test_booking_validation(self):
        slot = tomorrow_slot(self.project)
        response = self.client.post(reverse('confirm', args=['exp-1']), {'slot': slot.pk, 'mail': 'bad'})
        self.assertContains(response, '入力内容をご確認ください')
        self.assertFalse(Reservation.objects.exists())

    def test_closed_slot_cannot_be_booked(self):
        slot = tomorrow_slot(self.project)
        slot.closed = True
        slot.save()
        data = {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com', 'data_reuse': 'no', 'extra4': 'no'}
        response = self.client.post(reverse('confirm', args=['exp-1']), data)
        self.assertContains(response, '申し訳ございません')

    def test_projects_are_separate(self):
        other = Project.objects.create(name='other')
        other.ensure_slots()
        slot = tomorrow_slot(other)
        response = self.client.post(reverse('entry', args=['exp-1']), {'slot': slot.pk})
        self.assertRedirects(response, reverse('timeframe', args=['exp-1']))


@override_settings(SCHEDULE_ADMIN_PASSWORD_HASH=TEST_HASH)
class SettingTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse('setting_home'))
        self.assertTrue(response['Location'].startswith(reverse('setting_login')))
        self.client.post(reverse('setting_login'), {'password': 'wrong'})
        self.assertEqual(self.client.get(reverse('setting_home')).status_code, 302)
        login(self.client)
        self.assertEqual(self.client.get(reverse('setting_home')).status_code, 200)

    def test_create_edit_delete_project(self):
        login(self.client)
        response = self.client.post(reverse('setting_home'), {'action': 'create', 'name': 'exp2'})
        self.assertRedirects(response, reverse('setting_project', args=['exp2']))
        project = Project.objects.get(name='exp2')
        self.assertTrue(project.slots.exists())
        today = datetime.date.today()
        self.assertEqual(project.period_start, today)
        self.assertEqual(project.period_end, today + datetime.timedelta(days=13))
        self.assertEqual((project.time_start, project.time_end), (datetime.time(9), datetime.time(21)))
        self.assertEqual((project.close_mode, project.close_value), ('hours', 2))

        bad = self.client.post(reverse('setting_home'), {'action': 'create', 'name': '日本語'})
        self.assertContains(bad, 'アルファベット')

        page = self.client.get(reverse('setting_project', args=['exp2']))
        self.assertContains(page, '予約状況カレンダー')

        data = {
            'name': 'exp2b', 'consent_text': '同意してください', 'complete_text': '完了',
            'complete_button_enabled': 'on', 'complete_button_text': '戻る', 'complete_button_url': 'https://example.com',
            'use_full_name': 'on', 'use_extra1': 'on', 'title_extra1': '所属',
        }
        response = self.client.post(reverse('setting_project', args=['exp2']), data)
        # プロジェクト名は変えられない（name を送っても無視する）
        self.assertRedirects(response, reverse('setting_project', args=['exp2']))
        project.refresh_from_db()
        self.assertEqual(project.name, 'exp2')
        self.assertNotContains(self.client.get(reverse('setting_project', args=['exp2'])), 'name="name"')
        self.assertFalse(project.use_mail)
        self.assertEqual([f['title'] for f in project.fields()], ['氏名', '所属'])

        # 説明書はモーダルからアップロードし、チェックを外すと削除する
        fetch = {'HTTP_X_REQUESTED_WITH': 'fetch'}
        url = reverse('setting_project', args=['exp2'])
        bad = self.client.post(url, {'action': 'manual', 'manual': SimpleUploadedFile('a.txt', b'x')}, **fetch).json()
        self.assertFalse(bad['ok'])
        self.assertIn('PDF', bad['errors']['manual'][0])
        self.assertFalse(self.client.post(url, {'action': 'manual'}, **fetch).json()['ok'])
        self.client.post(url, {'action': 'manual', 'manual': SimpleUploadedFile('manual.pdf', b'%PDF-1.4')}, **fetch)
        project.refresh_from_db()
        self.assertEqual(bytes(project.manual_data), b'%PDF-1.4')
        self.assertEqual(project.manual_name, 'manual.pdf')
        self.client.post(url, {'action': 'manual_clear'}, **fetch)
        project.refresh_from_db()
        self.assertIsNone(project.manual_data)

        # その他を取得するのに項目名がない、ボタンの遷移先が javascript: は保存しない
        bad = self.client.post(reverse('setting_project', args=['exp2']), {
            'name': 'exp2b', 'use_extra2': 'on', 'complete_button_enabled': 'on',
            'complete_button_text': 'x', 'complete_button_url': 'javascript:alert(1)',
        })
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, '項目名を入力してください')
        self.assertContains(bad, 'https:// で始まるURL')
        self.assertContains(bad, 'href="/setting/home/exp2/appointments"')

        response = self.client.post(reverse('setting_home'), {'action': 'delete', 'id': project.pk})
        self.assertFalse(Project.objects.exists())
        self.assertFalse(Slot.objects.exists())

    def test_period_form(self):
        login(self.client)
        project = Project.objects.create(name='p1')
        project.ensure_slots()
        url = reverse('setting_project', args=['p1'])
        later = datetime.date.today() + datetime.timedelta(days=200)
        response = self.client.post(url, {'action': 'period', 'period_start': str(datetime.date.today()),
                                          'period_end': str(later), 'time_start': '09:00', 'time_end': '18:00',
                                          'close': 'hours:2', 'duration_hours': '0', 'duration_minutes': '30'})
        self.assertRedirects(response, url)
        project.refresh_from_db()
        self.assertEqual((project.period_end, project.time_start, project.time_end),
                         (later, datetime.time(9), datetime.time(18)))
        self.assertTrue(project.slots.filter(start__date=later).exists())  # 90日より先の終了日でも枠を作る

        bad = self.client.post(url, {'action': 'period', 'period_start': str(later), 'period_end': str(datetime.date.today()),
                                     'time_start': '18:00', 'time_end': '09:00', 'close': 'hours:2', 'duration_hours': '0', 'duration_minutes': '30'})
        self.assertContains(bad, '終了日は開始日より後にしてください')
        self.assertContains(bad, '終了時刻は開始時刻より後に')

    def test_autosave(self):
        login(self.client)
        project = Project.objects.create(name='auto')
        url = reverse('setting_project', args=['auto'])
        fetch = {'HTTP_X_REQUESTED_WITH': 'fetch'}
        period = {'action': 'period', 'period_start': str(project.period_start), 'period_end': str(project.period_end),
                  'time_start': '09:00', 'time_end': '21:00', 'close': 'today:0',
                  'duration_hours': '0', 'duration_minutes': '40'}
        response = self.client.post(url, period, **fetch)
        self.assertTrue(response.json()['ok'])
        self.assertIn('starts', response.json())
        project.refresh_from_db()
        self.assertEqual((project.duration, project.slot_count, project.buffer_enabled), (40, 2, False))
        # バッファをオンにすると、送られた時間で保存する
        response = self.client.post(url, {**period, 'buffer_enabled': 'on', 'buffer_side': 'after', 'buffer_minutes': '90'}, **fetch)
        project.refresh_from_db()
        self.assertEqual((project.buffer_enabled, project.buffer_side, project.buffer_minutes), (True, 'after', 90))
        # オフにすると、選んでいた値は残したまま無効にする（選べない欄は送られてこない）
        self.client.post(url, period, **fetch)
        project.refresh_from_db()
        self.assertEqual((project.buffer_enabled, project.buffer_side, project.buffer_minutes), (False, 'after', 90))
        self.assertEqual(project.buffer_after, datetime.timedelta(0))
        # 誤りはJSONで返し、保存しない
        bad = self.client.post(url, {**period, 'duration_minutes': '0'}, **fetch).json()
        self.assertFalse(bad['ok'])
        self.assertIn('duration_minutes', bad['errors'])
        project.refresh_from_db()
        self.assertEqual(project.duration, 40)
        # 文言などの設定も自動保存
        response = self.client.post(url, {'action': 'settings', 'consent_text': 'こんにちは', 'use_mail': 'on'}, **fetch)
        self.assertEqual(response.json(), {'ok': True})
        project.refresh_from_db()
        self.assertEqual(project.consent_text, 'こんにちは')
        page = self.client.get(url)
        self.assertNotContains(page, '設定を保存')
        self.assertContains(page, '使用する時間枠：<b id="slot-count">2</b>つ')

    def test_slot_count(self):
        from .models import slot_count
        self.assertEqual([slot_count(m) for m in (10, 30, 40, 60, 70, 290)], [1, 1, 2, 2, 3, 10])

    def test_close_setting_form(self):
        login(self.client)
        project = Project.objects.create(name='p3')
        url = reverse('setting_project', args=['p3'])
        base = {'action': 'period', 'period_start': str(project.period_start), 'period_end': str(project.period_end),
                'time_start': '09:00', 'time_end': '21:00', 'duration_hours': '0', 'duration_minutes': '30'}
        page = self.client.get(url)
        self.assertContains(page, '<option value="hours:2" selected>今から2時間以内</option>', html=False)
        for value, expected in [('hours:24', ('hours', 24)), ('today:0', ('today', 0)),
                                ('tomorrow:0', ('tomorrow', 0)), ('days:7', ('days', 7))]:
            self.client.post(url, {**base, 'close': value})
            project.refresh_from_db()
            self.assertEqual((project.close_mode, project.close_value), expected)
        self.assertContains(self.client.get(url), '<option value="days:7" selected>')
        bad = self.client.post(url, {**base, 'close': 'hours:25'})
        self.assertEqual(bad.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.close_mode, 'days')

    def test_admin_states(self):
        project = Project.objects.create(name='p2', period_start=datetime.date.today(),
                                         time_start=datetime.time(9), time_end=datetime.time(18))
        project.ensure_slots()
        slot = tomorrow_slot(project, 10)
        self.assertEqual(state(project, slot), 'open')
        self.assertEqual(state(project, slot, slot.start + datetime.timedelta(minutes=1)), 'none')  # 過ぎた枠
        self.assertEqual(state(project, tomorrow_slot(project, 8)), 'none')  # 時間帯の外
        r = Reservation.objects.create(slot=slot)
        self.assertEqual(state(project, slot, slot.start + datetime.timedelta(hours=1)), 'reserved')  # 予約は過ぎても残す
        r.status = 'paid'
        r.save()
        self.assertEqual(state(project, slot), 'paid')

        login(self.client)
        page = self.client.get(reverse('setting_project', args=['p2']))
        self.assertContains(page, 'mark--paid')
        response = self.client.post(reverse('setting_slots', args=['p2']), {'ids': [tomorrow_slot(project, 8).pk]})
        self.assertEqual(response.json()['states'], {})  # 期間外は切り替えない
        from .calendar import admin_week_starts
        starts, index = admin_week_starts(project)
        self.assertEqual(starts[index], datetime.date.today())
        week = self.client.get(reverse('setting_week', args=['p2']) + f'?start={starts[index + 1]}')
        self.assertContains(week, 'class="grid-wrap week"')

    def test_toggle_slots(self):
        login(self.client)
        project = Project.objects.create(name='exp3')
        project.ensure_slots()
        a, b = tomorrow_slot(project, 9), tomorrow_slot(project, 10)
        reserved = tomorrow_slot(project, 11)
        Reservation.objects.create(slot=reserved)
        url = reverse('setting_slots', args=['exp3'])
        response = self.client.post(url, {'ids': [a.pk, b.pk, reserved.pk]})
        self.assertEqual(response.json()['states'], {str(a.pk): 'closed', str(b.pk): 'closed'})
        a.refresh_from_db()
        self.assertTrue(a.closed)
        reserved.refresh_from_db()
        self.assertFalse(reserved.closed)
        response = self.client.post(url, {'ids': [a.pk]})
        self.assertEqual(response.json()['states'], {str(a.pk): 'open'})

        # ドラッグで選んだ範囲は1つずつ反転する（予約の入った枠は変えない）
        response = self.client.post(url, {'ids': [a.pk, b.pk, reserved.pk], 'mode': 'invert'})
        self.assertEqual(response.json()['states'], {str(a.pk): 'closed', str(b.pk): 'open'})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.closed, b.closed), (True, False))

    def test_appointments(self):
        login(self.client)
        project = Project.objects.create(name='exp4', use_full_name=True, use_mail=False, use_sex=True)
        project.ensure_slots()
        r1 = Reservation.objects.create(slot=tomorrow_slot(project, 9), full_name='Bさん', sex='male', mail='hidden@example.com')
        later = datetime.date.today() + datetime.timedelta(days=5)
        r2 = Reservation.objects.create(
            slot=Slot.objects.get(project=project, start=datetime.datetime.combine(later, datetime.time(9))),
            full_name='Aさん',
        )
        url = reverse('setting_appointments', args=['exp4'])
        page = self.client.get(url)
        self.assertContains(page, '男性')
        self.assertNotContains(page, 'hidden@example.com')  # 取得していない項目は出さない
        self.assertNotContains(page, 'メールアドレス')
        content = page.content.decode()
        self.assertLess(content.index('Bさん'), content.index('Aさん'))

        content = self.client.get(url + '?sort=full_name').content.decode()
        self.assertLess(content.index('Aさん'), content.index('Bさん'))

        filtered = self.client.get(url + f'?from={later}&to={later}')
        self.assertContains(filtered, 'Aさん')
        self.assertNotContains(filtered, 'Bさん')

        response = self.client.post(url, {'action': 'status', 'id': r1.pk, 'status': 'no_show'})
        self.assertEqual(response.json(), {'status': 'no_show'})
        self.assertEqual(self.client.post(url, {'action': 'status', 'id': r1.pk, 'status': 'bad'}).status_code, 400)
        r1.refresh_from_db()
        self.assertEqual(r1.status, 'no_show')

        # ステータスで絞り込む（複数選べる）・件数の見出し・ステータスでも並べ替えられる
        page = self.client.get(url + '?status=no_show&status=paid')
        self.assertContains(page, '1件の予約')
        self.assertContains(page, 'Bさん')
        self.assertNotContains(page, 'Aさん')
        self.assertContains(self.client.get(url), '2件の予約')
        content = self.client.get(url + '?sort=status').content.decode()
        self.assertLess(content.index('Aさん'), content.index('Bさん'))  # 予約済み → No Show の順
        content = self.client.get(url + '?sort=-sex').content.decode()  # どの列でも並べ替えられる
        self.assertLess(content.index('Bさん'), content.index('Aさん'))

        response = self.client.post(url, {'action': 'delete', 'id': r2.pk, 'query': 'sort=-date'})
        self.assertRedirects(response, url + '?sort=-date')
        self.assertFalse(Reservation.objects.filter(pk=r2.pk).exists())
        self.assertTrue(Slot.objects.filter(pk=r2.slot_id).exists())


class MailTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name='mailexp', use_full_name=True, use_mail=True,
            mail_enabled=True, mail_reply_to='lab@example.com',
            mail_subject='{日時}のご予約',
            mail_body='{氏名} 様\n日時：{日時}\nhttps://example.com/zoom\n変更：{キャンセル用URL}\n問い合わせ：{返信用メールアドレス}\n',
        )
        self.project.ensure_slots()

    def test_confirmation_mail(self):
        slot = tomorrow_slot(self.project)
        data = {'slot': slot.pk, 'full_name': '山田太郎', 'mail': 'a@example.com'}
        self.client.post(reverse('confirm', args=['mailexp']), data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['a@example.com'])
        self.assertEqual(message.reply_to, ['lab@example.com'])
        self.assertIn('問い合わせ：lab@example.com', message.body)
        token = Reservation.objects.get(slot=slot).token
        self.assertIn(f'変更：http://testserver/mailexp/reservation/{token}', message.body)
        self.assertEqual(message.subject, slot.label(with_year=True) + 'のご予約')
        self.assertIn('山田太郎 様', message.body)
        self.assertIn('https://example.com/zoom', message.body)
        # 「予約メールを自分も受け取る」（初期値オン）なら、返信用メールアドレスにもBCCで送る
        self.assertEqual(message.bcc, ['lab@example.com'])
        # 二度押ししても2通目は送らない
        self.client.post(reverse('confirm', args=['mailexp']), data)
        self.assertEqual(len(mail.outbox), 1)

    def test_no_bcc_when_off(self):
        self.project.mail_bcc_self = False
        self.project.save()
        slot = tomorrow_slot(self.project)
        self.client.post(reverse('confirm', args=['mailexp']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        self.assertEqual(mail.outbox[0].bcc, [])

    def test_cancel_mail(self):
        self.project.mail_cancel_subject = 'キャンセル：{日時}'
        self.project.mail_cancel_body = '{氏名} 様\n{日時} のご予約をキャンセルしました。'
        self.project.save()
        slot = Slot.objects.get(project=self.project, start=datetime.datetime.combine(
            datetime.date.today() + datetime.timedelta(days=2), datetime.time(10)))
        r = Reservation.objects.create(slot=slot, full_name='山田', mail='a@example.com')
        self.client.post(reverse('cancel', args=['mailexp', r.token]))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'キャンセル：' + slot.label(with_year=True))
        self.assertIn('山田 様', message.body)
        self.assertEqual(message.bcc, ['lab@example.com'])
        self.assertEqual(message.reply_to, ['lab@example.com'])

    def test_no_reply_to_when_empty(self):
        self.project.mail_reply_to = ''
        self.project.save()
        slot = tomorrow_slot(self.project)
        self.client.post(reverse('confirm', args=['mailexp']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        self.assertEqual(mail.outbox[0].reply_to, [])

    def test_no_mail_when_disabled(self):
        self.project.mail_enabled = False
        self.project.save()
        slot = tomorrow_slot(self.project)
        self.client.post(reverse('confirm', args=['mailexp']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_booking_saved_even_if_mail_fails(self):
        slot = tomorrow_slot(self.project)
        with override_settings(EMAIL_BACKEND='schedule.tests.FailingBackend'):
            response = self.client.post(reverse('confirm', args=['mailexp']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        self.assertRedirects(response, reverse('complete', args=['mailexp']))
        self.assertTrue(Reservation.objects.filter(slot=slot).exists())


from django.core.mail.backends.base import BaseEmailBackend  # noqa: E402


class FailingBackend(BaseEmailBackend):
    def send_messages(self, messages):
        raise ConnectionError('SMTPにつながらない')


@override_settings(SCHEDULE_ADMIN_PASSWORD_HASH=TEST_HASH)
class MailSettingTests(TestCase):
    def test_mail_requires_email_field(self):
        login(self.client)
        project = Project.objects.create(name='m1', use_mail=False)
        response = self.client.post(reverse('setting_project', args=['m1']), {
            'name': 'm1', 'use_full_name': 'on', 'mail_enabled': 'on', 'mail_subject': 's', 'mail_body': 'b',
        })
        self.assertContains(response, '「メールアドレス」を「取得する」にしてください')
        project.refresh_from_db()
        self.assertFalse(project.mail_enabled)

        response = self.client.post(reverse('setting_project', args=['m1']), {
            'name': 'm1', 'use_mail': 'on', 'mail_enabled': 'on', 'mail_reply_to': 'bad',
            'mail_subject': 's', 'mail_body': 'b',
        })
        self.assertEqual(response.status_code, 200)

        # 返信用メールアドレスは必須
        response = self.client.post(reverse('setting_project', args=['m1']), {
            'name': 'm1', 'use_mail': 'on', 'mail_enabled': 'on',
            'mail_subject': 's', 'mail_body': 'b', 'mail_cancel_subject': 'c', 'mail_cancel_body': 'd',
        })
        self.assertContains(response, '返信用メールアドレスを入力してください')

        response = self.client.post(reverse('setting_project', args=['m1']), {
            'name': 'm1', 'use_mail': 'on', 'mail_enabled': 'on', 'mail_reply_to': 'me@example.com',
            'mail_subject': 's', 'mail_body': 'b', 'mail_cancel_subject': 'c', 'mail_cancel_body': 'd',
        })
        self.assertRedirects(response, reverse('setting_project', args=['m1']))
        project.refresh_from_db()
        self.assertTrue(project.mail_enabled)
        self.assertEqual(project.mail_reply_to, 'me@example.com')
        self.assertEqual((project.mail_cancel_subject, project.mail_cancel_body), ('c', 'd'))
        self.assertFalse(project.mail_bcc_self)  # チェックを外して送った

    def test_mail_fields_kept_while_disabled(self):
        # 確認メールを送らないあいだは、メールの欄は入力できない（送られてこない）ので、今の値のままにする
        login(self.client)
        project = Project.objects.create(name='m2', mail_reply_to='me@example.com', mail_subject='件名')
        response = self.client.post(reverse('setting_project', args=['m2']), {'use_mail': 'on', 'use_full_name': 'on'})
        self.assertRedirects(response, reverse('setting_project', args=['m2']))
        project.refresh_from_db()
        self.assertFalse(project.mail_enabled)
        self.assertEqual((project.mail_reply_to, project.mail_subject), ('me@example.com', '件名'))
        self.assertTrue(project.mail_bcc_self)


class ManageReservationTests(TestCase):
    """予約確認メールの {キャンセル用URL} から開く、予約の確認・変更・キャンセル"""

    def setUp(self):
        self.project = Project.objects.create(name='mng', duration=60, use_full_name=True, use_mail=True, mail_enabled=True)
        self.project.ensure_slots()
        day = datetime.date.today() + datetime.timedelta(days=2)
        self.slot = lambda h, m=0: Slot.objects.get(project=self.project, start=datetime.datetime.combine(day, datetime.time(h, m)))
        self.r = Reservation.objects.create(slot=self.slot(10), duration=60, full_name='山田', mail='a@example.com')
        self.url = reverse('manage', args=['mng', self.r.token])

    def test_manage_page(self):
        page = self.client.get(self.url)
        self.assertContains(page, self.r.label())
        self.assertContains(page, '日時を変更する')
        self.project.duration = 40
        self.project.save()
        self.assertContains(self.client.get(self.url), '<td>1時間</td>')  # 予約したときの所要時間
        self.assertEqual(self.client.get(reverse('manage', args=['mng', 'wrong'])).status_code, 404)

    def test_cancel(self):
        response = self.client.post(reverse('cancel', args=['mng', self.r.token]))
        self.assertContains(response, '予約をキャンセルしました')
        self.assertFalse(Reservation.objects.exists())
        self.assertTrue(can_book(self.project, self.slot(10)))

    def test_change(self):
        # 自分の予約は空きとして扱うので、30分後ろにずらすこともできる
        page = self.client.get(reverse('change', args=['mng', self.r.token]))
        self.assertContains(page, '日時の変更')
        self.assertContains(page, 'この日時に変更する')
        self.assertContains(page, f'value="{self.slot(10, 30).pk}"')
        response = self.client.post(reverse('change', args=['mng', self.r.token]), {'slot': self.slot(10, 30).pk})
        self.assertRedirects(response, self.url + '?changed=1')
        self.r.refresh_from_db()
        self.assertEqual(self.r.slot_id, self.slot(10, 30).pk)
        self.assertEqual(self.r.full_name, '山田')  # 入力した内容はそのまま
        self.assertEqual(len(mail.outbox), 1)      # 変更後の日時で確認メールを送る
        self.assertIn('10:30', mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].subject.startswith('【日時の変更が完了しました】' + self.project.mail_subject))
        self.assertContains(self.client.get(self.url + '?changed=1'), '<h2>日時の変更が完了しました</h2>')

    def test_change_to_unavailable(self):
        Reservation.objects.create(slot=self.slot(14), duration=60, full_name='別の人')
        response = self.client.post(reverse('change', args=['mng', self.r.token]), {'slot': self.slot(13, 30).pk})
        self.assertContains(response, 'この日時には変更できなくなりました')
        self.r.refresh_from_db()
        self.assertEqual(self.r.slot_id, self.slot(10).pk)

    def test_past_reservation_cannot_change(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        Slot.objects.create(project=self.project, start=datetime.datetime.combine(yesterday, datetime.time(10)))
        past = Reservation.objects.create(
            slot=Slot.objects.get(project=self.project, start=datetime.datetime.combine(yesterday, datetime.time(10))))
        page = self.client.get(reverse('manage', args=['mng', past.token]))
        self.assertContains(page, '変更・キャンセルできません')
        self.client.post(reverse('cancel', args=['mng', past.token]))
        self.assertTrue(Reservation.objects.filter(pk=past.pk).exists())


class PageTextTests(TestCase):
    """最初の画面・予約完了画面の、ページタイトル（h2）と本文（1行ずつ <p>）"""

    def test_paragraphs(self):
        project = Project.objects.create(
            name='txt', consent_title='ご協力のお願い',
            consent_text='1行目\r\n<a href="example.com">あああ</a>を読んでください\n\nhttps://example.com/x を見てください\n<ul><li>項目</li></ul>',
        )
        html = project.consent_html()
        self.assertIn('<p>1行目</p>', html)
        self.assertIn('<p><a href="https://example.com">あああ</a>を読んでください</p>', html)
        self.assertIn('<br>', html)
        self.assertIn('<a href="https://example.com/x" target="_blank" rel="noopener">https://example.com/x</a>', html)
        self.assertIn('\n<ul><li>項目</li></ul>', html)
        project.ensure_slots()
        page = self.client.get(reverse('consent', args=['txt']))
        self.assertContains(page, '<h2>ご協力のお願い</h2>')

    def test_links_keep_scheme(self):
        project = Project(consent_text='<a href="https://a.com">a</a> <a href="/x">x</a> <a href="mailto:m@a.com">m</a>')
        html = project.consent_html()
        self.assertIn('href="https://a.com"', html)
        self.assertIn('href="/x"', html)
        self.assertIn('href="mailto:m@a.com"', html)
        self.assertNotIn('https://https', html)

    def test_complete_title(self):
        project = Project.objects.create(name='c', complete_title='{日時} 予約完了', complete_text='{日時} です')
        project.ensure_slots()
        slot = tomorrow_slot(project)
        self.client.post(reverse('confirm', args=['c']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        page = self.client.get(reverse('complete', args=['c']))
        self.assertContains(page, f'<h2>{slot.label(with_year=True)} 予約完了</h2>')
        self.assertContains(page, f'<p>{slot.label(with_year=True)} です</p>')

    def test_data_reuse_question(self):
        project = Project(use_data_reuse=True)
        field = [f for f in project.fields() if f['key'] == 'data_reuse'][0]
        self.assertEqual(field['title'], '関連研究でデータを再利用してもよろしいですか？（同意は任意です）')
        self.assertEqual(field['header'], 'データ再利用の許可')

    def test_old_text_split(self):
        import importlib
        migration = importlib.import_module('schedule.migrations.0007_titles_cancel_mail_bcc')
        title, body = migration.split('<h2>見出し</h2>\n<p>1行目</p>\n<p>2行目</p>')
        self.assertEqual((title, body), ('見出し', '1行目\n2行目'))


@override_settings(SCHEDULE_ADMIN_PASSWORD_HASH=TEST_HASH)
class PublishTests(TestCase):
    """公開中・停止中"""

    def setUp(self):
        login(self.client)
        self.project = Project.objects.create(name='pub', use_full_name=True, use_mail=False)
        self.project.ensure_slots()
        self.url = reverse('setting_project', args=['pub'])
        self.fetch = {'HTTP_X_REQUESTED_WITH': 'fetch'}

    def test_stop_and_publish(self):
        self.assertTrue(self.project.published)  # 作ったときは公開中
        bad = self.client.post(self.url, {'action': 'publish', 'published': '0', 'closed_message': ' '}, **self.fetch)
        self.assertFalse(bad.json()['ok'])
        self.client.post(self.url, {'action': 'publish', 'published': '0', 'closed_message': '募集は終了しました。'}, **self.fetch)
        self.project.refresh_from_db()
        self.assertFalse(self.project.published)
        self.assertContains(self.client.get(self.url), '停止中')

        # 停止中は文言だけを出し、日時の選択・申し込みはできない
        consent = self.client.get(reverse('consent', args=['pub']))
        self.assertContains(consent, '<p>募集は終了しました。</p>')
        self.assertNotContains(consent, '次へ進む')
        self.assertRedirects(self.client.get(reverse('timeframe', args=['pub'])), reverse('consent', args=['pub']))
        slot = tomorrow_slot(self.project)
        self.client.post(reverse('confirm', args=['pub']), {'slot': slot.pk, 'full_name': 'x'})
        self.assertFalse(Reservation.objects.exists())

        self.client.post(self.url, {'action': 'publish', 'published': '1'}, **self.fetch)
        self.project.refresh_from_db()
        self.assertTrue(self.project.published)
        self.assertEqual(self.project.closed_message, '募集は終了しました。')  # 次に停止するときの初期値
        self.assertContains(self.client.get(reverse('consent', args=['pub'])), '次へ進む')

    def test_admin_calendar_shows_recruit_hours(self):
        self.project.time_start = datetime.time(9)
        self.project.time_end = datetime.time(12)
        self.project.save()
        page = self.client.get(self.url).content.decode()
        page = page[page.index('id="week-area"'):]  # カレンダーの部分だけ見る
        self.assertIn('>9:00<', page)
        self.assertIn('>11:30<', page)
        self.assertNotIn('>8:30<', page)
        self.assertNotIn('>12:00<', page)


@override_settings(SCHEDULE_ADMIN_PASSWORD_HASH=TEST_HASH)
class CompleteButtonTests(TestCase):
    """予約完了画面の遷移ボタン（設置する・しない）"""

    def test_button_toggle(self):
        login(self.client)
        project = Project.objects.create(name='btn', use_full_name=True, use_mail=False)
        url = reverse('setting_project', args=['btn'])
        # 設置するのに文言・遷移先が空ならエラー
        response = self.client.post(url, {'use_full_name': 'on', 'complete_button_enabled': 'on'})
        self.assertContains(response, '遷移ボタンの文言を入力してください')
        self.assertContains(response, '遷移先のリンクを入力してください')
        self.client.post(url, {'use_full_name': 'on', 'complete_button_enabled': 'on',
                               'complete_button_text': 'アンケートへ', 'complete_button_url': 'https://example.com/q'})
        project.refresh_from_db()
        self.assertTrue(project.complete_button_enabled)
        # 外しても文言・遷移先は残る（入力欄は送られてこない）
        self.client.post(url, {'use_full_name': 'on'})
        project.refresh_from_db()
        self.assertFalse(project.complete_button_enabled)
        self.assertEqual((project.complete_button_text, project.complete_button_url), ('アンケートへ', 'https://example.com/q'))
        # 設置しないあいだは、予約完了画面にボタンを出さない
        project.ensure_slots()
        slot = tomorrow_slot(project)
        self.client.post(reverse('confirm', args=['btn']), {'slot': slot.pk, 'full_name': 'x'})
        self.assertNotContains(self.client.get(reverse('complete', args=['btn'])), 'アンケートへ')
        project.complete_button_enabled = True
        project.save()
        self.assertContains(self.client.get(reverse('complete', args=['btn'])), 'アンケートへ')
