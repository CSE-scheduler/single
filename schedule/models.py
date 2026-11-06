import datetime
import re
import secrets

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

# 募集期間の時刻として選べるもの（8:00〜23:00の30分ごと）
TIME_OPTIONS = [
    (datetime.datetime.combine(datetime.date.today(), datetime.time(START_HOUR))
     + datetime.timedelta(minutes=SLOT_MINUTES * i)).time()
    for i in range(N_SLOTS + 1)
]


def default_period_start():
    # 募集期間の初期値：プロジェクトを作った日から2週間（13日後まで）。作ったあとは自動では動かさない
    return datetime.date.today()


def default_period_end():
    return datetime.date.today() + datetime.timedelta(days=13)


# 予約を自動で締め切る枠の範囲。hours：今からn時間以内、today：今日中、tomorrow：次の日まで、days：今日からn日後まで
CLOSE_MODES = [('hours', '今からn時間以内'), ('today', '今日中'), ('tomorrow', '次の日まで'), ('days', '今日からn日後まで')]
CLOSE_HOURS_MAX = 24
CLOSE_DAYS_MAX = 7

# 所要時間（30分〜4時間の30分刻み）と、予約の前後を自動で閉じる時間（バッファ）
# 所要時間は 0〜4時間 と 00〜50分（10分刻み）で選ぶ。予約は30分の枠を、所要時間に足りるだけ使う
DURATION_HOURS = list(range(0, 5))
DURATION_MINUTES = list(range(0, 60, 10))
BUFFER_SIDES = [('before', '予約の前'), ('after', '予約の後ろ'), ('both', '予約の前後')]
BUFFER_CHOICES = [30, 60, 90, 120]


def slot_count(minutes):
    """所要時間に使う30分の枠の数（例：30分→1つ、40分〜1時間→2つ）"""
    return max(1, -(-minutes // SLOT_MINUTES))


def minutes_label(minutes):
    # 例：30 → 「30分」、90 → 「1時間30分」
    hours, rest = divmod(minutes, 60)
    return (f'{hours}時間' if hours else '') + (f'{rest}分' if rest or not hours else '')


def time_range_label(start, minutes, with_year=False):
    # 例：「11月5日(木) 10:30〜11:30」
    end = start + datetime.timedelta(minutes=minutes)
    year = f'{start.year}年' if with_year else ''
    return f'{year}{start.month}月{start.day}日({DAY_NAMES[start.weekday()]}) {start:%-H:%M}〜{end:%-H:%M}'


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


# 入力画面に出す項目名（その他1〜6以外は変えられない）。ここに書いていない項目は FIELDS の項目名を出す
FIELD_QUESTIONS = {
    'data_reuse': '関連研究でデータを再利用してもよろしいですか？（同意は任意です）',
}

# 最初の画面（同意画面）と予約完了画面は、ページタイトル（h2）と本文に分けて設定する
DEFAULT_CONSENT_TITLE = '実験へのご協力のお願い'
DEFAULT_CONSENT_TEXT = (
    'この度は実験へのご参加をご検討いただきありがとうございます。\n'
    '下の「説明書を読む」から説明書をお読みいただき、内容にご同意いただける場合は「次へ進む」を押して、日時をお選びください。'
)
DEFAULT_COMPLETE_TITLE = 'お申し込みが完了しました'
DEFAULT_COMPLETE_TEXT = (
    '{日時} でご予約を承りました。\n'
    '当日はどうぞよろしくお願いいたします。'
)

DEFAULT_MAIL_SUBJECT = '【実験】ご予約の確認'
DEFAULT_MAIL_BODY = (
    '{氏名} 様\n\n'
    'この度は実験にお申し込みいただきありがとうございます。\n'
    '下記の日時でご予約を承っております。\n\n'
    '日時：{日時}\n\n'
    '当日はどうぞよろしくお願いいたします。\n\n'
    '▼予約の変更・キャンセルはこちらからお願いします。\n'
    '{キャンセル用URL}\n\n'
    '※本メールアドレスは送信専用です。\n'
    'お問い合わせ：{返信用メールアドレス}\n'
)
DEFAULT_CANCEL_SUBJECT = '【実験】ご予約のキャンセル'
DEFAULT_CANCEL_BODY = (
    '{氏名} 様\n\n'
    '下記の日時のご予約をキャンセルしました。\n\n'
    '日時：{日時}\n\n'
    'またのご参加をお待ちしております。\n\n'
    '※本メールアドレスは送信専用です。\n'
    'お問い合わせ：{返信用メールアドレス}\n'
)

# 予約のステータス（予約一覧で変える）と、設定画面のカレンダーでの記号
RESERVATION_STATUSES = [
    ('reserved', '予約済み'),
    ('done', '実施済み（謝金未払い）'),
    ('paid', '謝金支払い済み'),
    ('no_show', 'No Show'),
    ('test', 'テスト用'),
]
STATUS_MARKS = {'reserved': '予', 'done': '未', 'paid': '済', 'no_show': 'N', 'test': 'テ'}


def new_token():
    # 予約の確認・変更・キャンセルのページのURLに使う、推測できない文字列
    return secrets.token_urlsafe(16)


# 1行がまるごとこれらのタグで始まるときは <p> で囲まない（リストや表などをそのまま書けるように）
_BLOCK_LINE = re.compile(r'^\s*</?(?:h[1-6]|p|div|ul|ol|li|table|thead|tbody|tr|th|td|hr|blockquote)\b', re.I)
# href="example.com" のように https:// のないリンクには https:// をつける（つけないと、このサイトの中のページになる）
_HREF = re.compile(r'(href\s*=\s*["\'])(?!https?:|mailto:|tel:|/|#)', re.I)
# タグの外にそのまま書いたURLはリンクにする
_BARE_URL = re.compile(r'(?<![="\'>/\w])(https?://[^\s<>"\']+)')


def _paragraphs(text):
    """設定画面で入力した本文を、1行ずつ <p> にする（空の行は1行ぶんの余白）。
    行の途中のHTMLタグ（<a href="...">リンク</a>、<strong>強調</strong> など）はそのまま使える。
    入力できるのは設定画面に入れる人だけなので、HTMLは消さない"""
    text = _HREF.sub(r'\1https://', text.replace('\r\n', '\n'))
    text = _BARE_URL.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
    html = []
    for line in text.strip('\n').split('\n'):
        if not line.strip():
            html.append('<br>')
        elif _BLOCK_LINE.match(line):
            html.append(line)
        else:
            html.append(f'<p>{line}</p>')
    return mark_safe('\n'.join(html))


class Project(models.Model):
    name = models.CharField('プロジェクト名', max_length=100, unique=True, validators=[validate_project_name])
    created_at = models.DateTimeField(auto_now_add=True)
    # この日までの枠を作ってある（毎回枠を数えなくて済むように覚えておく）
    slots_until = models.DateField(null=True, blank=True, editable=False)

    # 募集期間（参加者に見せる日付と時間帯）。期間外の枠は予約できない
    period_start = models.DateField('募集開始日', default=default_period_start)
    period_end = models.DateField('募集終了日', default=default_period_end)
    time_start = models.TimeField('一番早い時刻', default=datetime.time(9))
    time_end = models.TimeField('一番遅い時刻', default=datetime.time(21))
    # この範囲に始まる枠は、予約を自動で締め切る（例：close_mode='hours', close_value=2 → 今から2時間以内に始まる枠）
    close_mode = models.CharField(max_length=10, choices=CLOSE_MODES, default='hours')
    close_value = models.PositiveSmallIntegerField(default=2)
    # 所要時間（分）。予約するとこの時間ぶんの枠がふさがる
    duration = models.PositiveSmallIntegerField('所要時間', default=SLOT_MINUTES)
    # バッファ：buffer_enabled のとき、予約された枠の前・後ろ・前後を buffer_minutes 分だけ自動で閉じる
    buffer_enabled = models.BooleanField(default=False)
    buffer_side = models.CharField(max_length=10, choices=BUFFER_SIDES, default='both')
    buffer_minutes = models.PositiveSmallIntegerField(default=30)

    # 最初の画面（同意画面）
    consent_title = models.CharField('最初の画面のページタイトル', max_length=200, blank=True, default=DEFAULT_CONSENT_TITLE)
    consent_text = models.TextField('最初の画面の本文', blank=True, default=DEFAULT_CONSENT_TEXT)
    # 説明書はデータベースに入れる（サーバーのファイルを気にせず、MySQL・SQLiteのどちらでも使える）
    manual_data = models.BinaryField(null=True, blank=True, editable=False)
    manual_name = models.CharField(max_length=255, blank=True, default='', editable=False)
    manual_type = models.CharField(max_length=100, blank=True, default='', editable=False)

    # 予約完了画面
    complete_title = models.CharField('予約完了画面のページタイトル', max_length=200, blank=True, default=DEFAULT_COMPLETE_TITLE)
    complete_text = models.TextField('予約完了画面の本文', blank=True, default=DEFAULT_COMPLETE_TEXT)
    complete_button_text = models.CharField('遷移ボタンの文言', max_length=200, blank=True, default='')
    complete_button_url = models.CharField('遷移ボタンの遷移先', max_length=2000, blank=True, default='')

    # 予約確認メール（予約が完了したとき・日時を変更したときに送る）と、キャンセルのメール
    mail_enabled = models.BooleanField('確認メールを送る', default=False)
    # 返信用メールアドレス（メールの返信先。本文の {返信用メールアドレス} にも入る）
    mail_reply_to = models.EmailField('返信用メールアドレス', blank=True, default='')
    # 返信用メールアドレスにもBCCで送る（予約・キャンセルの通知の代わり）
    mail_bcc_self = models.BooleanField('予約メールを自分も受け取る', default=True)
    mail_subject = models.CharField('件名', max_length=200, blank=True, default=DEFAULT_MAIL_SUBJECT)
    mail_body = models.TextField('本文', blank=True, default=DEFAULT_MAIL_BODY)
    mail_cancel_subject = models.CharField('キャンセルのメールの件名', max_length=200, blank=True, default=DEFAULT_CANCEL_SUBJECT)
    mail_cancel_body = models.TextField('キャンセルのメールの本文', blank=True, default=DEFAULT_CANCEL_BODY)

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
        """入力画面に出す項目名"""
        default = FIELD_QUESTIONS.get(key) or dict((k, label) for k, label, _, _ in FIELDS)[key]
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
                # 予約一覧の列見出し（その他1〜6は設定した項目名、それ以外は短い名前）
                'header': self.field_title(key) if editable else label,
            })
        return result

    def consent_html(self):
        return _paragraphs(self.consent_text)

    def complete_title_text(self, date_text):
        return self.complete_title.replace('{日時}', date_text)

    def complete_html(self, date_text):
        return _paragraphs(self.complete_text.replace('{日時}', date_text))

    def in_period(self, start):
        """この時刻に始まる枠が募集期間（日付と時間帯）の中か"""
        return (self.period_start <= start.date() <= self.period_end
                and self.time_start <= start.time() < self.time_end)

    def close_cutoff(self, now):
        """これより前に始まる枠は予約を締め切る（参加者には×、設定画面では-）"""
        midnight = datetime.datetime.combine(now.date(), datetime.time())
        if self.close_mode == 'today':
            return midnight + datetime.timedelta(days=1)
        if self.close_mode == 'tomorrow':
            return midnight + datetime.timedelta(days=2)
        if self.close_mode == 'days':
            return midnight + datetime.timedelta(days=self.close_value + 1)
        return now + datetime.timedelta(hours=self.close_value)

    @property
    def buffer_before(self):
        minutes = self.buffer_minutes if self.buffer_enabled and self.buffer_side in ('before', 'both') else 0
        return datetime.timedelta(minutes=minutes)

    @property
    def buffer_after(self):
        minutes = self.buffer_minutes if self.buffer_enabled and self.buffer_side in ('after', 'both') else 0
        return datetime.timedelta(minutes=minutes)

    @property
    def slot_count(self):
        return slot_count(self.duration)

    def duration_label(self):
        return minutes_label(self.duration)

    def close_label(self):
        if self.close_mode == 'hours':
            return f'今から{self.close_value}時間以内'
        if self.close_mode == 'days':
            return f'今日から{self.close_value}日後まで'
        return dict(CLOSE_MODES)[self.close_mode]

    def ensure_slots(self, today=None):
        """今日から DAYS_AHEAD 日後（募集終了日がもっと先ならその日）までの枠をそろえる。
        すでにある枠（受付停止・予約）はそのまま"""
        today = today or datetime.date.today()
        last = max(today + datetime.timedelta(days=DAYS_AHEAD), self.period_end)
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

    def label(self, minutes=SLOT_MINUTES, with_year=False):
        return time_range_label(self.start, minutes, with_year)

    @property
    def reserved(self):
        try:
            return self.reservation is not None
        except Reservation.DoesNotExist:
            return False



class Reservation(models.Model):
    slot = models.OneToOneField(Slot, on_delete=models.CASCADE, related_name='reservation')
    created_at = models.DateTimeField(auto_now_add=True)
    # 予約したときの所要時間（分）。あとでプロジェクトの所要時間を変えても、この予約は変わらない
    duration = models.PositiveSmallIntegerField(default=SLOT_MINUTES)

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

    # ステータス（予約一覧の画面で変える）
    status = models.CharField('ステータス', max_length=10, choices=RESERVATION_STATUSES, default='reserved')
    # 参加者が予約の確認・変更・キャンセルをするページのURLに使う
    token = models.CharField(max_length=32, unique=True, default=new_token, editable=False)

    class Meta:
        ordering = ['slot__start']

    def __str__(self):
        return f'{self.slot} {self.full_name or self.mail}'

    @property
    def start(self):
        return self.slot.start

    @property
    def end(self):
        return self.slot.start + datetime.timedelta(minutes=self.duration)

    @property
    def occupied_end(self):
        """この予約がふさぐ枠の終わり（所要時間を30分の枠に切り上げる。例：10:00から40分 → 11:00）"""
        return self.slot.start + datetime.timedelta(minutes=SLOT_MINUTES * slot_count(self.duration))

    def label(self, with_year=False):
        return time_range_label(self.slot.start, self.duration, with_year)

    def duration_label(self):
        return minutes_label(self.duration)

    def display(self, key):
        value = getattr(self, key)
        if key == 'sex':
            return self.get_sex_display()
        if value is True:
            return 'はい'
        if value is False:
            return 'いいえ'
        return '' if value is None else value
