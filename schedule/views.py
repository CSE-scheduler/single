"""参加者が使う画面：同意画面 → 日時選択 → 入力 → 予約完了"""

import datetime
from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .calendar import user_week, user_week_starts
from .forms import reservation_form, reservation_values
from .mail import send_confirmation
from .models import Project, Reservation, Slot


def _project(name):
    project = get_object_or_404(Project, name=name)
    project.ensure_slots()
    return project


def _session_key(project):
    return f'schedule_reservation_{project.pk}'


def consent(request, project):
    project = _project(project)
    return render(request, 'schedule/consent.html', {'project': project})


def manual(request, project):
    project = get_object_or_404(Project, name=project)
    if not project.manual_data:
        raise Http404
    response = HttpResponse(bytes(project.manual_data), content_type=project.manual_type)
    response['Content-Disposition'] = f"inline; filename*=UTF-8''{quote(project.manual_name)}"
    return response


def timeframe(request, project):
    project = _project(project)
    starts = user_week_starts(project)
    selected = request.POST.get('slot', '') or request.GET.get('slot', '')
    # 最初は1週間分だけ作る。入力画面から戻ってきたときは、選んでいた日時の週を開く
    index = 0
    slot = _get_slot(project, selected)
    if slot and starts:
        index = min(max((slot.start.date() - starts[0]).days // 7, 0), len(starts) - 1)
    params = {
        'project': project,
        'starts': [d.isoformat() for d in starts],
        'index': index,
        'week': user_week(project, starts[index], selected) if starts else None,
    }
    return render(request, 'schedule/timeframe.html', params)


def week(request, project):
    """日時選択で「前の週・次の週」を押したときに読み込む1週間分の表"""
    project = get_object_or_404(Project, name=project)
    try:
        first = datetime.date.fromisoformat(request.GET.get('start', ''))
    except ValueError:
        raise Http404
    if first not in user_week_starts(project):
        raise Http404
    return render(request, 'schedule/_user_week.html', {'week': user_week(project, first)})


def _get_slot(project, slot_id):
    try:
        return Slot.objects.select_related('reservation').get(project=project, pk=int(slot_id))
    except (Slot.DoesNotExist, ValueError, TypeError):
        return None


def entry(request, project, form=None):
    project = _project(project)
    slot = _get_slot(project, request.POST.get('slot') or request.GET.get('slot'))
    if slot is None:
        return redirect('timeframe', project.name)
    if form is None:
        form = reservation_form(project)
    return render(request, 'schedule/entry.html', {'project': project, 'slot': slot, 'form': form})


def _message(request, project, title, message):
    return render(request, 'schedule/message.html', {
        'project': project, 'title': title, 'message': message, 'back_to_timeframe': True,
    })


def confirm(request, project):
    project = _project(project)
    if request.method != 'POST':
        return redirect('timeframe', project.name)

    form = reservation_form(project, request.POST)
    if not form.is_valid():
        return entry(request, project.name, form)

    key = _session_key(project)
    try:
        with transaction.atomic():
            # 同じ枠に2人が同時に申し込んでも、先の1人だけが予約できるように枠の行をロックする
            try:
                slot = Slot.objects.select_for_update().get(project=project, pk=int(request.POST.get('slot', '')))
            except (Slot.DoesNotExist, ValueError):
                return redirect('timeframe', project.name)
            slot.project = project
            existing = Reservation.objects.filter(slot=slot).first()
            # 申し込みボタンの二度押しや再読み込みは、同じ人の予約としてそのまま完了画面を出す
            if existing and existing.pk == request.session.get(key):
                return redirect('complete', project.name)
            if existing or not slot.bookable(datetime.datetime.now()):
                return _message(request, project, '申し訳ございません',
                                'この日時は予約できなくなりました。お手数ですが、日時を選択しなおしてください。')
            reservation = Reservation.objects.create(slot=slot, **reservation_values(form))
    except IntegrityError:
        # ロックが効かないデータベース（SQLite）で同時に申し込まれたとき
        return _message(request, project, '申し訳ございません',
                        'この日時はすでに予約が入りました。お手数ですが、日時を選択しなおしてください。')

    request.session[key] = reservation.pk
    # 予約確認メール（送れなくても予約は保存済みなので、エラー画面にはしない）
    send_confirmation(reservation)
    return redirect('complete', project.name)


def complete(request, project):
    project = _project(project)
    reservation = Reservation.objects.filter(
        pk=request.session.get(_session_key(project)), slot__project=project,
    ).select_related('slot').first()
    if reservation is None:
        return redirect('consent', project.name)
    return render(request, 'schedule/complete.html', {
        'project': project,
        'text': project.complete_html(reservation.slot.label(with_year=True)),
    })
