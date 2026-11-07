import datetime
import os

from django import forms

from .models import (
    BUFFER_CHOICES, BUFFER_SIDES, CLOSE_DAYS_MAX, CLOSE_HOURS_MAX, DURATION_HOURS, DURATION_MINUTES, FIELDS,
    SEX_CHOICES, TIME_OPTIONS, Project, validate_project_name,
)

# 説明書としてアップロードできるファイル（拡張子 → 配信するときの種類）
MANUAL_TYPES = {
    '.pdf': 'application/pdf',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
}
MANUAL_MAX_BYTES = 10 * 1024 * 1024

USE_FIELDS = [f'use_{key}' for key, _, _, _ in FIELDS]
TITLE_FIELDS = [f'title_{key}' for key, _, _, editable in FIELDS if editable]


class NewProjectForm(forms.Form):
    name = forms.CharField(max_length=100, validators=[validate_project_name])

    def clean_name(self):
        name = self.cleaned_data['name']
        if Project.objects.filter(name=name).exists():
            raise forms.ValidationError('同じ名前のプロジェクトがすでにあります。')
        return name


TIME_CHOICES = [(f'{t:%H:%M}', f'{t:%-H:%M}') for t in TIME_OPTIONS]
# 募集終了日は、今日から1年後まで（枠を作りすぎないように）
MAX_PERIOD_DAYS = 365


# 予約を自動で締め切る範囲の選択肢（値は「種類:数」）
CLOSE_CHOICES = (
    [(f'hours:{n}', f'今から{n}時間以内') for n in range(1, CLOSE_HOURS_MAX + 1)]
    + [('today:0', '今日中'), ('tomorrow:0', '次の日まで')]
    + [(f'days:{n}', f'今日から{n}日後まで') for n in range(1, CLOSE_DAYS_MAX + 1)]
)


class PeriodForm(forms.ModelForm):
    """募集予約カレンダーの設定（募集期間・所要時間・自動で閉鎖する枠・バッファ）"""
    time_start = forms.TypedChoiceField(choices=TIME_CHOICES[:-1], coerce=lambda v: datetime.time.fromisoformat(v))
    time_end = forms.TypedChoiceField(choices=TIME_CHOICES[1:], coerce=lambda v: datetime.time.fromisoformat(v))
    close = forms.ChoiceField(choices=CLOSE_CHOICES)
    duration_hours = forms.TypedChoiceField(choices=[(h, str(h)) for h in DURATION_HOURS], coerce=int)
    duration_minutes = forms.TypedChoiceField(choices=[(m, f'{m:02d}') for m in DURATION_MINUTES], coerce=int)
    # バッファを設けないときは、これらの欄は送られてこない（入力できない）ので、今の値のままにする
    buffer_side = forms.ChoiceField(choices=BUFFER_SIDES, required=False)
    buffer_minutes = forms.TypedChoiceField(choices=[(m, str(m)) for m in BUFFER_CHOICES], coerce=int,
                                            required=False, empty_value=None)

    class Meta:
        model = Project
        fields = ['period_start', 'period_end', 'time_start', 'time_end', 'buffer_enabled', 'buffer_side', 'buffer_minutes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            project = self.instance
            self.initial['time_start'] = f'{project.time_start:%H:%M}'
            self.initial['time_end'] = f'{project.time_end:%H:%M}'
            value = project.close_value if project.close_mode in ('hours', 'days') else 0
            self.initial['close'] = f'{project.close_mode}:{value}'
            self.initial['duration_hours'], self.initial['duration_minutes'] = divmod(project.duration, 60)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('period_start'), cleaned.get('period_end')
        if start and end:
            if start > end:
                self.add_error('period_end', '終了日は開始日より後にしてください。')
            elif end > datetime.date.today() + datetime.timedelta(days=MAX_PERIOD_DAYS):
                self.add_error('period_end', '終了日は今日から1年以内にしてください。')
        t_start, t_end = cleaned.get('time_start'), cleaned.get('time_end')
        if t_start and t_end and t_start >= t_end:
            self.add_error('time_end', '終了時刻は開始時刻より後にしてください。')
        hours, minutes = cleaned.get('duration_hours'), cleaned.get('duration_minutes')
        if hours is not None and minutes is not None:
            if hours * 60 + minutes == 0:
                self.add_error('duration_minutes', '所要時間を入力してください。')
            else:
                self.instance.duration = hours * 60 + minutes
        if cleaned.get('close'):
            mode, value = cleaned['close'].split(':')
            self.instance.close_mode = mode
            self.instance.close_value = int(value)
        if not cleaned.get('buffer_side'):
            cleaned['buffer_side'] = self.instance.buffer_side
        if not cleaned.get('buffer_minutes'):
            cleaned['buffer_minutes'] = self.instance.buffer_minutes
        return cleaned


# 「確認メールを送る」をオンにするまで入力できない欄（送られてこないので、今の値のままにする）
MAIL_FIELDS = ['mail_reply_to', 'mail_bcc_self', 'mail_subject', 'mail_body', 'mail_cancel_subject', 'mail_cancel_body']


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'consent_title', 'consent_text', 'complete_title', 'complete_text',
            'complete_button_enabled', 'complete_button_text', 'complete_button_url',
            *USE_FIELDS, *TITLE_FIELDS,
            'mail_enabled', *MAIL_FIELDS,
        ]

    def clean_complete_button_url(self):
        url = self.cleaned_data['complete_button_url'].strip()
        if url and not url.startswith(('http://', 'https://', '/')):
            raise forms.ValidationError('遷移先は http:// か https:// で始まるURLを入力してください。')
        return url

    def clean(self):
        cleaned = super().clean()
        for key, label, _, editable in FIELDS:
            if editable and cleaned.get(f'use_{key}') and not cleaned.get(f'title_{key}', '').strip():
                self.add_error(f'title_{key}', f'「{label}」を取得するときは、項目名を入力してください。')
        if cleaned.get('complete_button_enabled'):
            if not cleaned.get('complete_button_text', '').strip():
                self.add_error('complete_button_text', '遷移ボタンの文言を入力してください。')
            if 'complete_button_url' not in self.errors and not cleaned.get('complete_button_url'):
                self.add_error('complete_button_url', '遷移先のリンクを入力してください。')
        else:
            # 設置しないあいだは入力欄が送られてこないので、今の値のままにする
            for name in ('complete_button_text', 'complete_button_url'):
                self.errors.pop(name, None)
                cleaned[name] = getattr(self.instance, name)
        if cleaned.get('mail_enabled'):
            if not cleaned.get('use_mail'):
                self.add_error('mail_enabled', '確認メールを送るときは、「メールアドレス」を「取得する」にしてください。')
            if 'mail_reply_to' not in self.errors and not cleaned.get('mail_reply_to'):
                self.add_error('mail_reply_to', '返信用メールアドレスを入力してください。')
            if not cleaned.get('mail_subject', '').strip() or not cleaned.get('mail_body', '').strip():
                self.add_error('mail_body', '確認メールのタイトルと本文を入力してください。')
            if not cleaned.get('mail_cancel_subject', '').strip() or not cleaned.get('mail_cancel_body', '').strip():
                self.add_error('mail_cancel_body', 'キャンセルのメールのタイトルと本文を入力してください。')
        else:
            for name in MAIL_FIELDS:
                self.errors.pop(name, None)
                cleaned[name] = getattr(self.instance, name)
        return cleaned


class ManualForm(forms.Form):
    """説明書のアップロード（モーダルから送る）"""
    manual = forms.FileField(error_messages={'required': '説明書のファイルを選んでください。'})

    def clean_manual(self):
        manual = self.cleaned_data['manual']
        ext = os.path.splitext(manual.name)[1].lower()
        if ext not in MANUAL_TYPES:
            raise forms.ValidationError('説明書は PDF・PNG・JPEG のファイルをアップロードしてください。')
        if manual.size > MANUAL_MAX_BYTES:
            raise forms.ValidationError(f'説明書のファイルは {MANUAL_MAX_BYTES // 1024 // 1024}MB 以下にしてください。')
        return manual

    def save(self, project):
        manual = self.cleaned_data['manual']
        project.manual_data = manual.read()
        project.manual_name = os.path.basename(manual.name)
        project.manual_type = MANUAL_TYPES[os.path.splitext(manual.name)[1].lower()]
        project.save(update_fields=['manual_data', 'manual_name', 'manual_type'])


YES_NO = [('yes', 'はい'), ('no', 'いいえ')]


def reservation_form(project, data=None):
    """プロジェクトの設定で「取得する」にした項目だけの入力フォームを作る"""
    form = forms.Form(data)
    for field in project.fields():
        key, kind, title = field['key'], field['kind'], field['title']
        if kind == 'text':
            f = forms.CharField(label=title, max_length=200)
        elif kind == 'textarea':
            f = forms.CharField(label=title, widget=forms.Textarea(attrs={'rows': 3}))
        elif kind == 'age':
            f = forms.IntegerField(label=title, min_value=0, max_value=150)
        elif kind == 'sex':
            f = forms.ChoiceField(label=title, choices=SEX_CHOICES, widget=forms.RadioSelect)
        elif kind == 'email':
            f = forms.EmailField(label=title, max_length=254)
        else:  # bool
            f = forms.ChoiceField(label=title, choices=YES_NO, widget=forms.RadioSelect)
        f.kind = kind
        form.fields[key] = f
    return form


def reservation_values(form):
    # フォームの値を Reservation に入れる形にする（はい・いいえ → True・False）
    values = {}
    for key, field in form.fields.items():
        value = form.cleaned_data[key]
        values[key] = (value == 'yes') if field.kind == 'bool' else value
    return values
