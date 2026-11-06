import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import DAYS_AHEAD, N_SLOTS, Project, Reservation, Slot


def login(client):
    client.post(reverse('setting_login'), {'password': '1234'})


def tomorrow_slot(project, hour=10):
    day = datetime.date.today() + datetime.timedelta(days=1)
    return Slot.objects.get(project=project, start=datetime.datetime.combine(day, datetime.time(hour)))


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
        self.assertContains(response, 'mark--reserved">済')
        self.assertContains(response, 'mark--closed">×')

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


class SettingTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse('setting_home'))
        self.assertTrue(response['Location'].startswith(reverse('setting_login')))
        self.client.post(reverse('setting_login'), {'password': 'wrong'})
        self.assertEqual(self.client.get(reverse('setting_home')).status_code, 302)

    def test_create_edit_delete_project(self):
        login(self.client)
        response = self.client.post(reverse('setting_home'), {'action': 'create', 'name': 'exp2'})
        self.assertRedirects(response, reverse('setting_project', args=['exp2']))
        project = Project.objects.get(name='exp2')
        self.assertTrue(project.slots.exists())

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
