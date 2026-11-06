"""日時の表（参加者の日時選択と、設定画面のカレンダー）を1週間ずつ作る。

ページを開いたときは表示する週だけを作り、ほかの週は「前の週・次の週」を押したときに
（views.week / setting_views.week から）読み込む。"""

import datetime

import jpholiday
from django.db.models import Min

from .models import DAY_NAMES, TIME_OPTIONS

WEEK = datetime.timedelta(days=7)
ALL_TIMES = TIME_OPTIONS[:-1]  # 枠の始まる時刻（8:00〜22:30）


def _columns(first):
    columns = []
    for i in range(7):
        day = first + datetime.timedelta(days=i)
        holiday = jpholiday.is_holiday(day)
        columns.append({
            'date': day,
            # 月は表の左上に出すので、列の見出しは日にちだけ（1日だけは月も出す）
            'head': f'{day.month}/{day.day}' if day.day == 1 else str(day.day),
            'day_name': DAY_NAMES[day.weekday()],
            'kind': 'holiday' if holiday or day.weekday() == 6 else ('saturday' if day.weekday() == 5 else ''),
        })
    return columns


def _slots(project, first):
    slots = project.slots.filter(
        start__gte=datetime.datetime.combine(first, datetime.time()),
        start__lt=datetime.datetime.combine(first + WEEK, datetime.time()),
    ).select_related('reservation')
    return {(s.start.date(), s.start.time()): s for s in slots}


def _week(project, first, times, make_cell):
    columns = _columns(first)
    by_key = _slots(project, first)
    for slot in by_key.values():
        slot.project = project  # 枠ごとにプロジェクトを読み直さないように
    last = first + datetime.timedelta(days=6)
    rows = [
        {'time': f'{t:%-H:%M}', 'cells': [make_cell(by_key.get((c['date'], t))) for c in columns]}
        for t in times
    ]
    return {
        'start': first.isoformat(),
        'title': f'{first.month}/{first.day}〜{last.month}/{last.day}',
        'month': f'{first.month}月',
        'columns': columns,
        'rows': rows,
    }


# ---- 参加者用 ----

def user_week_starts(project, today=None):
    """参加者に見せる週の始まりの日。今日が一番左に来る（募集開始が1週間より先なら、その日が一番左）"""
    today = today or datetime.date.today()
    first = today if project.period_start < today + WEEK else project.period_start
    last = min(project.period_end, project.slots_until or project.period_end)
    starts = []
    while first <= last:
        starts.append(first)
        first += WEEK
    return starts


def user_week(project, first, selected='', now=None):
    now = now or datetime.datetime.now()
    times = [t for t in ALL_TIMES if project.time_start <= t < project.time_end]

    def cell(slot):
        if slot is None or not slot.bookable(now):
            return None  # 予約できない枠は、理由にかかわらず「×」
        return {'slot': slot, 'label': slot.label(), 'checked': str(slot.pk) == selected}

    return _week(project, first, times, cell)


# ---- 設定画面用 ----

def admin_week_starts(project, today=None):
    """設定画面で見られる週の始まりの日（今日を一番左にして、過去の予約も前の週で見られる）と、今日の週の番号"""
    today = today or datetime.date.today()
    earliest = project.slots.aggregate(first=Min('start'))['first']
    earliest = earliest.date() if earliest else today
    last = project.slots_until or today
    starts = []
    first = today
    while first + datetime.timedelta(days=6) >= earliest:
        starts.insert(0, first)
        first -= WEEK
    index = len(starts) - 1
    first = today + WEEK
    while first <= last:
        starts.append(first)
        first += WEEK
    return starts, index


def admin_week(project, first, now=None):
    now = now or datetime.datetime.now()

    def cell(slot):
        if slot is None:
            return {'state': 'none'}
        return {'state': slot.admin_state(now), 'slot': slot}

    return _week(project, first, ALL_TIMES, cell)
