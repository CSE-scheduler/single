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
            complete_text='予約：{日時}', complete_button_text='アンケートへ', complete_button_url='https://example.com/q',
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
        self.assertEqual((r.full_name, r.data_reuse, r.extra4, r.paid), ('山田太郎', True, False, False))

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
            'complete_button_text': '戻る', 'complete_button_url': 'https://example.com',
            'use_full_name': 'on', 'use_extra1': 'on', 'title_extra1': '所属',
            'manual': SimpleUploadedFile('manual.pdf', b'%PDF-1.4', content_type='application/pdf'),
        }
        response = self.client.post(reverse('setting_project', args=['exp2']), data)
        self.assertRedirects(response, reverse('setting_project', args=['exp2b']))
        project.refresh_from_db()
        self.assertEqual(project.name, 'exp2b')
        self.assertFalse(project.use_mail)
        self.assertEqual(bytes(project.manual_data), b'%PDF-1.4')
        self.assertEqual([f['title'] for f in project.fields()], ['氏名', '所属'])

        # その他を取得するのに項目名がない、ボタンの遷移先が javascript: は保存しない
        bad = self.client.post(reverse('setting_project', args=['exp2b']), {
            'name': 'exp2b', 'use_extra2': 'on', 'complete_button_text': 'x', 'complete_button_url': 'javascript:alert(1)',
        })
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, '項目名を入力してください')
        self.assertContains(bad, 'https:// で始まるURL')
        self.assertContains(bad, 'href="/setting/home/exp2b/appointments"')

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
                                          'close': 'hours:2', 'duration': '30', 'buffer_side': 'both', 'buffer_minutes': '0'})
        self.assertRedirects(response, url)
        project.refresh_from_db()
        self.assertEqual((project.period_end, project.time_start, project.time_end),
                         (later, datetime.time(9), datetime.time(18)))
        self.assertTrue(project.slots.filter(start__date=later).exists())  # 90日より先の終了日でも枠を作る

        bad = self.client.post(url, {'action': 'period', 'period_start': str(later), 'period_end': str(datetime.date.today()),
                                     'time_start': '18:00', 'time_end': '09:00', 'close': 'hours:2', 'duration': '30', 'buffer_side': 'both', 'buffer_minutes': '0'})
        self.assertContains(bad, '終了日は開始日より後にしてください')
        self.assertContains(bad, '一番遅い時刻は')

    def test_close_setting_form(self):
        login(self.client)
        project = Project.objects.create(name='p3')
        url = reverse('setting_project', args=['p3'])
        base = {'action': 'period', 'period_start': str(project.period_start), 'period_end': str(project.period_end),
                'time_start': '09:00', 'time_end': '21:00', 'duration': '30', 'buffer_side': 'both', 'buffer_minutes': '0'}
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
        r.paid = True
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

        response = self.client.post(url, {'action': 'paid', 'id': r1.pk, 'paid': '1'})
        self.assertEqual(response.json(), {'paid': True})
        r1.refresh_from_db()
        self.assertTrue(r1.paid)

        response = self.client.post(url, {'action': 'delete', 'id': r2.pk, 'query': 'sort=-date'})
        self.assertRedirects(response, url + '?sort=-date')
        self.assertFalse(Reservation.objects.filter(pk=r2.pk).exists())
        self.assertTrue(Slot.objects.filter(pk=r2.slot_id).exists())


class MailTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name='mailexp', use_full_name=True, use_mail=True,
            mail_enabled=True, mail_bcc='me@example.com',
            mail_subject='{日時}のご予約', mail_body='{氏名} 様\n日時：{日時}\nhttps://example.com/zoom\n',
        )
        self.project.ensure_slots()

    def test_confirmation_mail(self):
        slot = tomorrow_slot(self.project)
        data = {'slot': slot.pk, 'full_name': '山田太郎', 'mail': 'a@example.com'}
        self.client.post(reverse('confirm', args=['mailexp']), data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['a@example.com'])
        self.assertEqual(message.bcc, ['me@example.com'])
        self.assertEqual(message.subject, slot.label(with_year=True) + 'のご予約')
        self.assertIn('山田太郎 様', message.body)
        self.assertIn('https://example.com/zoom', message.body)
        # 二度押ししても2通目は送らない
        self.client.post(reverse('confirm', args=['mailexp']), data)
        self.assertEqual(len(mail.outbox), 1)

    def test_no_bcc_when_empty(self):
        self.project.mail_bcc = ''
        self.project.save()
        slot = tomorrow_slot(self.project)
        self.client.post(reverse('confirm', args=['mailexp']), {'slot': slot.pk, 'full_name': 'x', 'mail': 'a@example.com'})
        self.assertEqual(mail.outbox[0].bcc, [])

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
            'name': 'm1', 'use_mail': 'on', 'mail_enabled': 'on', 'mail_bcc': 'bad',
            'mail_subject': 's', 'mail_body': 'b',
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('setting_project', args=['m1']), {
            'name': 'm1', 'use_mail': 'on', 'mail_enabled': 'on', 'mail_bcc': 'me@example.com',
            'mail_subject': 's', 'mail_body': 'b',
        })
        self.assertRedirects(response, reverse('setting_project', args=['m1']))
        project.refresh_from_db()
        self.assertTrue(project.mail_enabled)
        self.assertEqual(project.mail_bcc, 'me@example.com')
