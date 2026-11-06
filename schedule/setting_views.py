"""実験者が使う設定画面（パスワードで保護）"""

import datetime
from functools import wraps
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .calendar import admin_week, admin_week_starts, toggleable
from .forms import CLOSE_CHOICES, TIME_CHOICES, TITLE_FIELDS, NewProjectForm, PeriodForm, ProjectForm
from .models import PROJECT_NAME_SYMBOLS, RESERVATION_STATUSES, Project, Reservation, Slot

SESSION_KEY = 'schedule_admin'


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            if request.headers.get('x-requested-with') == 'fetch':
                return JsonResponse({'error': 'ログインしなおしてください。'}, status=403)
            return redirect(f"{reverse('setting_login')}?next={quote(request.get_full_path())}")
        return view(request, *args, **kwargs)
    return wrapper


def login(request):
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ''
    error = ''
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if password and check_password(password, settings.SCHEDULE_ADMIN_PASSWORD_HASH):
            request.session.cycle_key()
            request.session[SESSION_KEY] = True
            return redirect(next_url or 'setting_home')
        error = 'パスワードが違います。'
    return render(request, 'schedule/setting/login.html', {'next': next_url, 'error': error})


@require_POST
def logout(request):
    request.session.pop(SESSION_KEY, None)
    return redirect('setting_login')


def root(request):
    return redirect('setting_home')


@admin_required
def home(request):
    form = NewProjectForm()
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            project = get_object_or_404(Project, pk=request.POST.get('id'))
            name = project.name
            project.delete()
            messages.success(request, f'プロジェクト「{name}」を削除しました。')
            return redirect('setting_home')
        form = NewProjectForm(request.POST)
        if form.is_valid():
            project = Project.objects.create(name=form.cleaned_data['name'])
            project.ensure_slots()
            messages.success(request, f'プロジェクト「{project.name}」を作成しました。文言や取得する項目を設定してください。')
            return redirect('setting_project', project.name)

    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time())
    projects = Project.objects.annotate(
        n_reservations=Count('slots__reservation'),
        n_upcoming=Count('slots__reservation', filter=Q(slots__start__gte=today_start)),
        n_paid=Count('slots__reservation', filter=Q(slots__reservation__status='paid')),
    )
    projects = list(projects)
    for project in projects:
        project.recruit_url = request.build_absolute_uri(reverse('consent', args=[project.name]))
    return render(request, 'schedule/setting/home.html', {
        'projects': projects, 'form': form, 'symbols': PROJECT_NAME_SYMBOLS,
    })


def _errors(form):
    return {name: [str(e) for e in errors] for name, errors in form.errors.items()}


@admin_required
def project_edit(request, project):
    project = get_object_or_404(Project, name=project)
    project.ensure_slots()
    # フォームの検証に失敗すると project.name が入力値に変わってしまうので、URLには元の名前を使う
    url_name = project.name
    form = ProjectForm(instance=project)
    period_form = PeriodForm(instance=project)
    # 設定は入力したその場で自動保存する（JavaScriptから送られ、結果をJSONで返す）
    autosave = request.headers.get('x-requested-with') == 'fetch'
    if request.method == 'POST' and request.POST.get('action') == 'period':
        period_form = PeriodForm(request.POST, instance=project)
        if period_form.is_valid():
            project = period_form.save()
            project.ensure_slots()
            if autosave:
                starts, index = admin_week_starts(project)
                return JsonResponse({'ok': True, 'starts': [d.isoformat() for d in starts], 'index': index})
            messages.success(request, '保存しました。')
            return redirect('setting_project', project.name)
        if autosave:
            return JsonResponse({'ok': False, 'errors': _errors(period_form)})
        messages.error(request, '入力に誤りがあります。')
        project = Project.objects.get(pk=project.pk)
        form = ProjectForm(instance=project)
    elif request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            manual_changed = bool(form.cleaned_data.get('manual') or form.cleaned_data.get('manual_clear'))
            project = form.save()
            if autosave:
                # 説明書を変えたときは、表示（今の説明書の名前）を新しくするために画面を読みなおす
                return JsonResponse({'ok': True, 'reload': manual_changed})
            messages.success(request, '保存しました。')
            return redirect('setting_project', project.name)
        if autosave:
            return JsonResponse({'ok': False, 'errors': _errors(form)})
        messages.error(request, '入力に誤りがあります。赤字の部分を確認してください。')

    fields = []
    for field in project.fields(only_used=False):
        fields.append({
            **field,
            'use': form[f"use_{field['key']}"],
            'title_field': form[f"title_{field['key']}"] if f"title_{field['key']}" in TITLE_FIELDS else None,
        })

    stored = Project.objects.get(pk=project.pk)  # カレンダーと説明書は保存済みの内容を出す
    # カレンダーは最初は今日の週だけを作り、ほかの週は「前の週・次の週」を押したときに読み込む
    starts, index = admin_week_starts(stored)
    return render(request, 'schedule/setting/project.html', {
        'project': stored,
        'url_name': url_name,
        'form': form,
        'period_form': period_form,
        'time_choices': TIME_CHOICES,
        'close_choices': CLOSE_CHOICES,
        'fields': fields,
        'starts': [d.isoformat() for d in starts],
        'index': index,
        'week': admin_week(stored, starts[index]),
        'n_reservations': Reservation.objects.filter(slot__project=stored).count(),
        'participant_url': request.build_absolute_uri(reverse('consent', args=[stored.name])),
    })


@admin_required
@never_cache
def week(request, project):
    """カレンダーで「前の週・次の週」を押したときに読み込む1週間分の表"""
    project = get_object_or_404(Project, name=project)
    try:
        first = datetime.date.fromisoformat(request.GET.get('start', ''))
    except ValueError:
        raise Http404
    if first not in admin_week_starts(project)[0]:
        raise Http404
    return render(request, 'schedule/setting/_admin_week.html', {'project': project, 'week': admin_week(project, first)})


@admin_required
@require_POST
def toggle_slots(request, project):
    """カレンダーのマス（または1日分・1時刻分）の受付を切り替える。
    予約が入っている枠と「-」の枠（締め切った枠・募集期間外・予約の前後で閉じた枠）は変えない"""
    project = get_object_or_404(Project, name=project)
    ids = [int(i) for i in request.POST.getlist('ids') if i.isdigit()]
    slots = toggleable(project, list(Slot.objects.filter(project=project, pk__in=ids)))
    # 1つでも受付中の枠があれば全部止める。全部止まっていれば全部再開する
    close = any(not s.closed for s in slots)
    Slot.objects.filter(pk__in=[s.pk for s in slots]).update(closed=close)
    return JsonResponse({'states': {s.pk: 'closed' if close else 'open' for s in slots}})


SORTS = {
    'date': ['slot__start'],
    '-date': ['-slot__start'],
    'full_name': ['full_name', 'slot__start'],
    '-full_name': ['-full_name', 'slot__start'],
}


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@admin_required
def appointments(request, project):
    project = get_object_or_404(Project, name=project)

    if request.method == 'POST':
        reservation = get_object_or_404(Reservation, pk=request.POST.get('id'), slot__project=project)
        action = request.POST.get('action')
        if action == 'status':
            status = request.POST.get('status')
            if status not in dict(RESERVATION_STATUSES):
                return JsonResponse({'error': 'ステータスが正しくありません。'}, status=400)
            reservation.status = status
            reservation.save(update_fields=['status'])
            return JsonResponse({'status': reservation.status})
        if action == 'delete':
            label = reservation.label(with_year=True)
            reservation.delete()
            messages.success(request, f'{label} の予約を削除しました（この枠は再び予約できるようになります）。')
            query = request.POST.get('query', '')
            url = reverse('setting_appointments', args=[project.name])
            return redirect(f'{url}?{query}' if query else url)
        return HttpResponseNotAllowed(['POST'])

    sort = request.GET.get('sort', 'date')
    if sort not in SORTS:
        sort = 'date'
    date_from = _parse_date(request.GET.get('from'))
    date_to = _parse_date(request.GET.get('to'))

    reservations = Reservation.objects.filter(slot__project=project).select_related('slot')
    if date_from:
        reservations = reservations.filter(slot__start__gte=datetime.datetime.combine(date_from, datetime.time()))
    if date_to:
        end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time())
        reservations = reservations.filter(slot__start__lt=end)
    reservations = reservations.order_by(*SORTS[sort])

    fields = project.fields()
    rows = [
        {'obj': r, 'date': r.label(with_year=True), 'values': [r.display(f['key']) for f in fields]}
        for r in reservations
    ]

    # 列見出しを押したときの並べ替え（同じ列をもう一度押すと逆順）
    def sort_link(key):
        new = f'-{key}' if sort == key else key
        params = {k: v for k, v in (('from', request.GET.get('from', '')), ('to', request.GET.get('to', ''))) if v}
        params['sort'] = new
        return '?' + urlencode(params)

    def sort_mark(key):
        return '▲' if sort == key else ('▼' if sort == f'-{key}' else '')

    sortable = {'full_name'}
    columns = [
        {**f, 'sort_link': sort_link(f['key']) if f['key'] in sortable else None,
         'sort_mark': sort_mark(f['key']) if f['key'] in sortable else ''}
        for f in fields
    ]

    return render(request, 'schedule/setting/appointments.html', {
        'project': project,
        'columns': columns,
        'rows': rows,
        'statuses': RESERVATION_STATUSES,
        'counts': [(label, sum(1 for r in rows if r['obj'].status == key)) for key, label in RESERVATION_STATUSES],
        'date_sort_link': sort_link('date'),
        'date_sort_mark': sort_mark('date'),
        'sort': sort,
        'date_from': request.GET.get('from', '') if date_from else '',
        'date_to': request.GET.get('to', '') if date_to else '',
        'query': request.GET.urlencode(),
    })
