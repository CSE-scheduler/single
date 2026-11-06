import datetime
import os

from django import forms

from .models import (
    BUFFER_CHOICES, BUFFER_SIDES, CLOSE_DAYS_MAX, CLOSE_HOURS_MAX, DURATION_CHOICES, FIELDS, SEX_CHOICES,
    TIME_OPTIONS, Project, minutes_label, validate_project_name,
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
    time_start = forms.TypedChoiceField(choices=TIME_CHOICES[:-1], coerce=lambda v: datetime.time.fromisoformat(v))
    time_end = forms.TypedChoiceField(choices=TIME_CHOICES[1:], coerce=lambda v: datetime.time.fromisoformat(v))
    close = forms.ChoiceField(choices=CLOSE_CHOICES)
    duration = forms.TypedChoiceField(choices=[(m, minutes_label(m)) for m in DURATION_CHOICES], coerce=int)
    buffer_side = forms.ChoiceField(choices=BUFFER_SIDES)
    buffer_minutes = forms.TypedChoiceField(
        choices=[(0, '閉じない')] + [(m, minutes_label(m)) for m in BUFFER_CHOICES if m], coerce=int,
    )

    class Meta:
        model = Project
        fields = ['period_start', 'period_end', 'time_start', 'time_end', 'duration', 'buffer_side', 'buffer_minutes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial['time_start'] = f'{self.instance.time_start:%H:%M}'
            self.initial['time_end'] = f'{self.instance.time_end:%H:%M}'
            value = self.instance.close_value if self.instance.close_mode in ('hours', 'days') else 0
            self.initial['close'] = f'{self.instance.close_mode}:{value}'

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
            self.add_error('time_end', '一番遅い時刻は、一番早い時刻より後にしてください。')
        if cleaned.get('close'):
            mode, value = cleaned['close'].split(':')
            self.instance.close_mode = mode
            self.instance.close_value = int(value)
        return cleaned


class ProjectForm(forms.ModelForm):
    manual = forms.FileField(required=False)
    manual_clear = forms.BooleanField(required=False)

    class Meta:
        model = Project
        fields = [
            'name', 'consent_text', 'complete_text', 'complete_button_text', 'complete_button_url',
            *USE_FIELDS, *TITLE_FIELDS,
            'mail_enabled', 'mail_subject', 'mail_bcc', 'mail_body',
        ]

    def clean_complete_button_url(self):
        url = self.cleaned_data['complete_button_url'].strip()
        if url and not url.startswith(('http://', 'https://', '/')):
            raise forms.ValidationError('遷移先は http:// か https:// で始まるURLを入力してください。')
        return url

    def clean_manual(self):
        manual = self.cleaned_data.get('manual')
        if not manual:
            return None
        ext = os.path.splitext(manual.name)[1].lower()
        if ext not in MANUAL_TYPES:
            raise forms.ValidationError('説明書は PDF・PNG・JPEG のファイルをアップロードしてください。')
        if manual.size > MANUAL_MAX_BYTES:
            raise forms.ValidationError(f'説明書のファイルは {MANUAL_MAX_BYTES // 1024 // 1024}MB 以下にしてください。')
        return manual

    def clean(self):
        cleaned = super().clean()
        for key, label, _, editable in FIELDS:
            if editable and cleaned.get(f'use_{key}') and not cleaned.get(f'title_{key}', '').strip():
                self.add_error(f'title_{key}', f'「{label}」を取得するときは、項目名を入力してください。')
        text = cleaned.get('complete_button_text', '').strip()
        url = cleaned.get('complete_button_url', '')
        if bool(text) != bool(url):
            self.add_error('complete_button_text', '遷移ボタンを出すときは、文言と遷移先の両方を入力してください（出さないときは両方とも空にします）。')
        if cleaned.get('mail_enabled'):
            if not cleaned.get('use_mail'):
                self.add_error('mail_enabled', '確認メールを送るときは、「メールアドレス」を「取得する」にしてください。')
            if not cleaned.get('mail_subject', '').strip() or not cleaned.get('mail_body', '').strip():
                self.add_error('mail_body', '件名と本文を入力してください。')
        return cleaned

    def save(self, commit=True):
        project = super().save(commit=False)
        manual = self.cleaned_data.get('manual')
        if manual:
            project.manual_data = manual.read()
            project.manual_name = os.path.basename(manual.name)
            project.manual_type = MANUAL_TYPES[os.path.splitext(manual.name)[1].lower()]
        elif self.cleaned_data.get('manual_clear'):
            project.manual_data = None
            project.manual_name = ''
            project.manual_type = ''
        if commit:
            project.save()
        return project


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
