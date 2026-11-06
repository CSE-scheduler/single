import datetime
import re

import jpholiday
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe


# ---- 枠の作り方 ----
# 今日から DAYS_AHEAD 日後までの枠が常にあるようにする（足りない分は画面を開いたときに自動で作る）
DAYS_AHEAD = 90
# 1日の枠：START_HOUR時から、SLOT_MINUTES分ごとに N_SLOTS 枠（8:00〜23:00）
START_HOUR = 8
SLOT_MINUTES = 30
N_SLOTS = 30

DAY_NAMES = ['月', '火', '水', '木', '金', '土', '日']


# ---- プロジェクト名 ----
# URLにそのまま使うので、アルファベット・数字・URLに入れても意味が変わらない記号だけにする
PROJECT_NAME_SYMBOLS = "-_.~!$&'()*+,;=:@"
PROJECT_NAME_RE = re.compile(r"[A-Za-z0-9" + re.escape(PROJECT_NAME_SYMBOLS) + r"]+")
# URLの最初の部分と重なる名前は使えない
RESERVED_PROJECT_NAMES = {'setting', 'admin', 'static'}


def validate_project_name(value):
    if not PROJECT_NAME_RE.fullmatch(value):
        raise ValidationError(f'プロジェクト名に使えるのは、アルファベット・数字・記号（{PROJECT_NAME_SYMBOLS}）だけです。')
    if set(value) == {'.'}:
        raise ValidationError('「.」だけの名前は使えません。')
    if value.lower() in RESERVED_PROJECT_NAMES:
        raise ValidationError(f'「{value}」はプロジェクト名に使えません。')


# ---- 予約のときに取得する項目 ----
# (項目のキー, 標準の項目名, 種類, 項目名を設定画面で変えられるか)
# 種類：text（1行の文字）, textarea（複数行の文字）, age（数字）, sex（選択）, email, bool（はい・いいえ）
FIELDS = [
    ('full_name', '氏名', 'text', False),
    ('age', '年齢', 'age', False),
    ('sex', '性別', 'sex', False),
    ('mail', 'メールアドレス', 'email', False),
    ('data_reuse', 'データ再利用の許可', 'bool', False),
    ('extra1', 'その他1', 'textarea', True),
    ('extra2', 'その他2', 'textarea', True),
    ('extra3', 'その他3', 'textarea', True),
    ('extra4', 'その他4', 'bool', True),
    ('extra5', 'その他5', 'bool', True),
    ('extra6', 'その他6', 'bool', True),
]

SEX_CHOICES = [('male', '男性'), ('female', '女性'), ('other', 'その他')]


DEFAULT_CONSENT_TEXT = (
    '<h2>実験へのご協力のお願い</h2>\n'
    '<p>この度は実験へのご参加をご検討いただきありがとうございます。</p>\n'
    '<p>下の「説明書を読む」から説明書をお読みいただき、内容にご同意いただける場合は「次へ進む」を押して、日時をお選びください。</p>'
)
DEFAULT_COMPLETE_TEXT = (
    '<h2>お申し込みが完了しました</h2>\n'
    '<p>{日時} でご予約を承りました。</p>\n'
    '<p>当日はどうぞよろしくお願いいたします。</p>'
)


# 行の終わりがこれらのタグなら、改行を <br> にしない（見出しや段落のあとに余計な空行ができないように）
_BLOCK_TAG_END = re.compile(r'(</?(?:h[1-6]|p|div|ul|ol|li|table|thead|tbody|tr|th|td|br|hr)\b[^>]*>)[ \t]*\n', re.I)
DEFAULT_MAIL_SUBJECT = '【実験】ご予約の確認'
DEFAULT_MAIL_BODY = (
    '{氏名} 様\n\n'
    'この度は実験にお申し込みいただきありがとうございます。\n'
    '下記の日時でご予約を承っております。\n\n'
    '日時：{日時}\n\n'
    '当日はどうぞよろしくお願いいたします。\n'
)


def _html(text):
    # 設定画面で入力した文言は、HTMLタグをそのまま使え、改行も反映する（入力できるのは設定画面に入れる人だけ）
    text = _BLOCK_TAG_END.sub(r'\1', text.replace('\r\n', '\n'))
    return mark_safe(text.replace('\n', '<br>'))


class Project(models.Model):
    name = models.CharField('プロジェクト名', max_length=100, unique=True, validators=[validate_project_name])
    created_at = models.DateTimeField(auto_now_add=True)
    # この日までの枠を作ってある（毎回枠を数えなくて済むように覚えておく）
    slots_until = models.DateField(null=True, blank=True, editable=False)

    # 最初の画面（同意画面）
    consent_text = models.TextField('最初の画面の文言', blank=True, default=DEFAULT_CONSENT_TEXT)
    # 説明書はデータベースに入れる（サーバーのファイルを気にせず、MySQL・SQLiteのどちらでも使える）
    manual_data = models.BinaryField(null=True, blank=True, editable=False)
    manual_name = models.CharField(max_length=255, blank=True, default='', editable=False)
    manual_type = models.CharField(max_length=100, blank=True, default='', editable=False)

    # 予約完了画面
    complete_text = models.TextField('予約完了画面の文言', blank=True, default=DEFAULT_COMPLETE_TEXT)
    complete_button_text = models.CharField('遷移ボタンの文言', max_length=200, blank=True, default='')
    complete_button_url = models.CharField('遷移ボタンの遷移先', max_length=2000, blank=True, default='')

    # 予約確認メール（予約が完了したときに送る）
    mail_enabled = models.BooleanField('確認メールを送る', default=False)
    mail_bcc = models.EmailField('BCC', blank=True, default='')
    mail_subject = models.CharField('件名', max_length=200, blank=True, default=DEFAULT_MAIL_SUBJECT)
    mail_body = models.TextField('本文', blank=True, default=DEFAULT_MAIL_BODY)

    # 予約のときに取得する項目（取得する・しない）
    use_full_name = models.BooleanField(default=True)
    use_age = models.BooleanField(default=False)
    use_sex = models.BooleanField(default=False)
    use_mail = models.BooleanField(default=True)
    use_data_reuse = models.BooleanField(default=False)
    use_extra1 = models.BooleanField(default=False)
    use_extra2 = models.BooleanField(default=False)
    use_extra3 = models.BooleanField(default=False)
    use_extra4 = models.BooleanField(default=False)
    use_extra5 = models.BooleanField(default=False)
    use_extra6 = models.BooleanField(default=False)
    # その他1〜6の項目名
    title_extra1 = models.CharField(max_length=500, blank=True, default='')
    title_extra2 = models.CharField(max_length=500, blank=True, default='')
    title_extra3 = models.CharField(max_length=500, blank=True, default='')
    title_extra4 = models.CharField(max_length=500, blank=True, default='')
    title_extra5 = models.CharField(max_length=500, blank=True, default='')
    title_extra6 = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def field_title(self, key):
        default = dict((k, label) for k, label, _, _ in FIELDS)[key]
        return getattr(self, f'title_{key}', '') or default

    def fields(self, only_used=True):
        # 設定画面・入力画面・予約一覧で使う項目の一覧
        result = []
        for key, label, kind, editable in FIELDS:
            used = getattr(self, f'use_{key}')
            if only_used and not used:
                continue
            result.append({
                'key': key, 'label': label, 'kind': kind, 'editable': editable,
                'used': used, 'title': self.field_title(key),
            })
        return result

    def consent_html(self):
        return _html(self.consent_text)

    def complete_html(self, date_text):
        return _html(self.complete_text.replace('{日時}', date_text))

    def ensure_slots(self, today=None):
        """今日から DAYS_AHEAD 日後までの枠をそろえる。すでにある枠（受付停止・予約）はそのまま"""
        today = today or datetime.date.today()
        last = today + datetime.timedelta(days=DAYS_AHEAD)
        if self.slots_until and self.slots_until >= last:
            return
        first = today
        if self.slots_until and self.slots_until >= today:
            first = self.slots_until + datetime.timedelta(days=1)
        new = []
        day = first
        while day <= last:
            start = datetime.datetime.combine(day, datetime.time(START_HOUR))
            for i in range(N_SLOTS):
                new.append(Slot(project=self, start=start + datetime.timedelta(minutes=SLOT_MINUTES * i)))
            day += datetime.timedelta(days=1)
        # 同時に2つの画面から作っても重ならないように、すでにある枠は無視する
        Slot.objects.bulk_create(new, batch_size=500, ignore_conflicts=True)
        Project.objects.filter(pk=self.pk).update(slots_until=last)
        self.slots_until = last


class Slot(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='slots')
    start = models.DateTimeField()
    # 実験者が受付を止めた枠（×）
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ['start']
        constraints = [models.UniqueConstraint(fields=['project', 'start'], name='unique_slot_per_project')]

    def __str__(self):
        return f'{self.project.name} {self.start:%Y-%m-%d %H:%M}'

    @property
    def end(self):
        return self.start + datetime.timedelta(minutes=SLOT_MINUTES)

    @property
    def is_holiday(self):
        return bool(jpholiday.is_holiday(self.start.date()))

    def label(self, with_year=False):
        # 例：「11月5日(木) 10:30〜11:00」
        day = self.start.date()
        day_name = DAY_NAMES[day.weekday()] + ('・祝' if self.is_holiday else '')
        year = f'{day.year}年' if with_year else ''
        return f'{year}{day.month}月{day.day}日({day_name}) {self.start:%-H:%M}〜{self.end:%-H:%M}'

    @property
    def reserved(self):
        try:
            return self.reservation is not None
        except Reservation.DoesNotExist:
            return False

    @property
    def state(self):
        # open：予約できる（◯）、closed：実験者が受付を止めた（×）、reserved：予約が入っている（済）
        if self.reserved:
            return 'reserved'
        return 'closed' if self.closed else 'open'


class Reservation(models.Model):
    slot = models.OneToOneField(Slot, on_delete=models.CASCADE, related_name='reservation')
    created_at = models.DateTimeField(auto_now_add=True)

    full_name = models.CharField('氏名', max_length=200, blank=True, default='')
    age = models.PositiveSmallIntegerField('年齢', null=True, blank=True)
    sex = models.CharField('性別', max_length=10, choices=SEX_CHOICES, blank=True, default='')
    mail = models.EmailField('メールアドレス', max_length=254, blank=True, default='')
    data_reuse = models.BooleanField('データ再利用の許可', null=True, blank=True)
    extra1 = models.TextField('その他1', blank=True, default='')
    extra2 = models.TextField('その他2', blank=True, default='')
    extra3 = models.TextField('その他3', blank=True, default='')
    extra4 = models.BooleanField('その他4', null=True, blank=True)
    extra5 = models.BooleanField('その他5', null=True, blank=True)
    extra6 = models.BooleanField('その他6', null=True, blank=True)

    # 謝金を支払い済みか（予約一覧の画面で変える）
    paid = models.BooleanField('謝金支払い済み', default=False)

    class Meta:
        ordering = ['slot__start']

    def __str__(self):
        return f'{self.slot} {self.full_name or self.mail}'

    def display(self, key):
        value = getattr(self, key)
        if key == 'sex':
            return self.get_sex_display()
        if value is True:
            return 'はい'
        if value is False:
            return 'いいえ'
        return '' if value is None else value
