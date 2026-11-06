"""参加者が使う画面：同意画面 → 日時選択 → 入力 → 予約完了、と予約の確認・変更・キャンセル"""

import datetime
from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .calendar import can_book, user_week, user_week_starts
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


def _timeframe_page(request, project, changing=None):
    """日時選択の画面。changing を渡すと、その予約の日時を変更する画面になる"""
    starts = user_week_starts(project)
    selected = request.POST.get('slot', '') or request.GET.get('slot', '')
    # 最初は1週間分だけ作る。入力画面から戻ってきたときは、選んでいた日時の週を開く
    index = 0
    slot = _get_slot(project, selected)
    if slot and starts:
        index = min(max((slot.start.date() - starts[0]).days // 7, 0), len(starts) - 1)
    week_url = reverse('week', args=[project.name])
    params = {
        'project': project,
        'starts': [d.isoformat() for d in starts],
        'index': index,
        'week': user_week(project, starts[index], selected, exclude=changing) if starts else None,
        'span': project.slot_count,
        'changing': changing,
    }
    if changing:
        params.update({
            'form_action': reverse('change', args=[project.name, changing.token]),
            'week_url': f'{week_url}?change={changing.token}',
            'back_url': reverse('manage', args=[project.name, changing.token]),
            'back_label': '予約の確認に戻る',
            'submit_label': 'この日時に変更する',
        })
    else:
        params.update({
            'form_action': reverse('entry', args=[project.name]),
            'week_url': week_url,
            'back_url': reverse('consent', args=[project.name]),
            'back_label': '最初の画面に戻る',
            'submit_label': '入力画面へ',
        })
    return render(request, 'schedule/timeframe.html', params)


# 日時選択と入力の画面はブラウザに保存させない（「戻る」でも最新の空き状況を出す）
@never_cache
def timeframe(request, project):
    return _timeframe_page(request, _project(project))


@never_cache
def week(request, project):
    """日時選択で「前の週・次の週」を押したときに読み込む1週間分の表"""
    project = get_object_or_404(Project, name=project)
    try:
        first = datetime.date.fromisoformat(request.GET.get('start', ''))
    except ValueError:
        raise Http404
    if first not in user_week_starts(project):
        raise Http404
    changing = None
    if request.GET.get('change'):
        changing = get_object_or_404(Reservation, token=request.GET['change'], slot__project=project)
    return render(request, 'schedule/_user_week.html', {'week': user_week(project, first, exclude=changing)})


def _get_slot(project, slot_id):
    try:
        return Slot.objects.select_related('reservation').get(project=project, pk=int(slot_id))
    except (Slot.DoesNotExist, ValueError, TypeError):
        return None


@never_cache
def entry(request, project, form=None):
    project = _project(project)
    slot = _get_slot(project, request.POST.get('slot') or request.GET.get('slot'))
    if slot is None:
        return redirect('timeframe', project.name)
    if not can_book(project, slot):
        # 日時選択の画面を開いたあとに、枠が閉じられたり予約が入ったりしたとき
        return _message(request, project, '申し訳ございません',
                        'この日時は予約できなくなりました。お手数ですが、日時を選択しなおしてください。')
    if form is None:
        form = reservation_form(project)
    return render(request, 'schedule/entry.html', {
        'project': project, 'slot': slot, 'date': slot.label(project.duration), 'form': form,
    })


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
            # 所要時間ぶんの枠が重ならないよう、同じプロジェクトの申し込みを1つずつ処理する
            Project.objects.select_for_update().get(pk=project.pk)
            existing = Reservation.objects.filter(slot=slot).first()
            # 申し込みボタンの二度押しや再読み込みは、同じ人の予約としてそのまま完了画面を出す
            if existing and existing.pk == request.session.get(key):
                return redirect('complete', project.name)
            if existing or not can_book(project, slot):
                return _message(request, project, '申し訳ございません',
                                'この日時は予約できなくなりました。お手数ですが、日時を選択しなおしてください。')
            reservation = Reservation.objects.create(slot=slot, duration=project.duration, **reservation_values(form))
    except IntegrityError:
        # ロックが効かないデータベース（SQLite）で同時に申し込まれたとき
        return _message(request, project, '申し訳ございません',
                        'この日時はすでに予約が入りました。お手数ですが、日時を選択しなおしてください。')

    request.session[key] = reservation.pk
    # 予約確認メール（送れなくても予約は保存済みなので、エラー画面にはしない）
    send_confirmation(reservation, _manage_url(request, reservation))
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
        'text': project.complete_html(reservation.label(with_year=True)),
    })


# ---- 予約の確認・変更・キャンセル（予約確認メールの {キャンセル用URL} から開く） ----

def _manage_url(request, reservation):
    return request.build_absolute_uri(reverse('manage', args=[reservation.slot.project.name, reservation.token]))


def _reservation(project, token):
    return get_object_or_404(Reservation.objects.select_related('slot'), token=token, slot__project=project)


def _editable(reservation):
    # 始まる前の予約だけ、変更・キャンセルできる
    return reservation.start > datetime.datetime.now()


@never_cache
def manage(request, project, token):
    project = _project(project)
    reservation = _reservation(project, token)
    return render(request, 'schedule/manage.html', {
        'project': project,
        'reservation': reservation,
        'editable': _editable(reservation),
        'changed': request.GET.get('changed') == '1',
    })


@never_cache
def change(request, project, token):
    project = _project(project)
    reservation = _reservation(project, token)
    manage_url = reverse('manage', args=[project.name, token])
    if not _editable(reservation):
        return redirect(manage_url)
    if request.method != 'POST':
        return _timeframe_page(request, project, changing=reservation)

    unavailable = render(request, 'schedule/message.html', {
        'project': project, 'title': '申し訳ございません',
        'message': 'この日時には変更できなくなりました。お手数ですが、日時を選択しなおしてください。',
        'back_url': reverse('change', args=[project.name, token]), 'back_label': '日時を選択しなおす',
    })
    try:
        with transaction.atomic():
            Project.objects.select_for_update().get(pk=project.pk)
            reservation = Reservation.objects.select_for_update().select_related('slot').get(pk=reservation.pk)
            try:
                slot = Slot.objects.get(project=project, pk=int(request.POST.get('slot', '')))
            except (Slot.DoesNotExist, ValueError):
                return redirect('change', project.name, token)
            if slot.pk == reservation.slot_id:
                return redirect(manage_url)
            if Reservation.objects.filter(slot=slot).exists() or not can_book(project, slot, exclude=reservation):
                return unavailable
            reservation.slot = slot
            reservation.duration = project.duration
            reservation.save(update_fields=['slot', 'duration'])
    except IntegrityError:
        return unavailable

    send_confirmation(reservation, _manage_url(request, reservation))
    return redirect(f'{manage_url}?changed=1')


def cancel(request, project, token):
    project = _project(project)
    reservation = _reservation(project, token)
    if request.method != 'POST' or not _editable(reservation):
        return redirect('manage', project.name, token)
    label = reservation.label(with_year=True)
    reservation.delete()
    return render(request, 'schedule/message.html', {
        'project': project, 'title': '予約をキャンセルしました',
        'message': f'{label} のご予約をキャンセルしました。',
        'back_url': reverse('timeframe', args=[project.name]), 'back_label': '別の日時で予約する',
    })
