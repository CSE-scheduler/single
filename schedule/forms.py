import os

from django import forms

from .models import FIELDS, SEX_CHOICES, Project, validate_project_name

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


class ProjectForm(forms.ModelForm):
    manual = forms.FileField(required=False)
    manual_clear = forms.BooleanField(required=False)

    class Meta:
        model = Project
        fields = [
            'name', 'consent_text', 'complete_text', 'complete_button_text', 'complete_button_url',
            *USE_FIELDS, *TITLE_FIELDS,
            'mail_enabled', 'mail_from', 'mail_on_booking', 'mail_2days', 'mail_1day', 'mail_1hour',
            'mail_subject', 'mail_body',
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
            if not cleaned.get('mail_from') and 'mail_from' not in self.errors:
                self.add_error('mail_from', '送信元アドレスを入力してください。')
            if not any(cleaned.get(f) for f in ('mail_on_booking', 'mail_2days', 'mail_1day', 'mail_1hour')):
                self.add_error('mail_enabled', '送るタイミングを1つ以上選んでください。')
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
