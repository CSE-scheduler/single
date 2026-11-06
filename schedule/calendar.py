"""日時の表（参加者の日時選択と、設定画面のカレンダー）と、枠が空いているかの判定。

ページを開いたときは表示する週だけを作り、ほかの週は「前の週・次の週」を押したときに
（views.week / setting_views.week から）読み込む。"""

import datetime

import jpholiday
from django.db.models import Min

from .models import DAY_NAMES, SLOT_MINUTES, STATUS_MARKS, TIME_OPTIONS, Reservation

WEEK = datetime.timedelta(days=7)
DAY = datetime.timedelta(days=1)
SLOT = datetime.timedelta(minutes=SLOT_MINUTES)
ALL_TIMES = TIME_OPTIONS[:-1]  # 枠の始まる時刻（8:00〜22:30）


def _steps(start, end):
    """start から end の手前まで、30分ごとの時刻"""
    t = start
    while t < end:
        yield t
        t += SLOT


class Availability:
    """first〜last（datetime）の範囲で、枠ごとの状態と、そこから予約できるかを判定する。

    - 予約は所要時間ぶんの枠をふさぐ（occupied）
    - 予約の前・後ろのバッファの枠も閉じる（blocked。予約でふさがった枠も含む）
    - 新しい予約は、ふさぐ枠がどれも空いていて、そのバッファに他の予約が入っていないときだけできる
    """

    def __init__(self, project, first, last, now=None, exclude=None):
        self.project = project
        self.now = now or datetime.datetime.now()
        self.cutoff = project.close_cutoff(self.now)
        self.need = SLOT * project.slot_count
        # 範囲の外にある予約やバッファも影響するので、前後1日ぶん余分に読む
        slots = project.slots.filter(start__gte=first - DAY, start__lt=last + DAY)
        self.slots = {s.start: s for s in slots}
        reservations = Reservation.objects.filter(
            slot__project=project, slot__start__gte=first - DAY, slot__start__lt=last + DAY,
        ).select_related('slot')
        if exclude is not None:
            # 日時を変更するときは、その人の今の予約はないものとして空きを調べる
            reservations = reservations.exclude(pk=exclude.pk)
        self.occupied = {}
        self.blocked = set()
        for r in reservations:
            for t in _steps(r.start, r.occupied_end):
                self.occupied[t] = r
            for t in _steps(r.start - project.buffer_before, r.occupied_end + project.buffer_after):
                self.blocked.add(t)

    def free(self, t):
        """この枠を新しい予約に使えるか（受付中・締め切り前・募集期間内・予約やバッファでふさがっていない）"""
        slot = self.slots.get(t)
        return (slot is not None and not slot.closed and t >= self.cutoff
                and self.project.in_period(t) and t not in self.blocked)

    def startable(self, t):
        """この時刻から所要時間ぶん予約できるか"""
        if not all(self.free(u) for u in _steps(t, t + self.need)):
            return False
        # 新しい予約のバッファに、他の予約が入っていないか
        zone = _steps(t - self.project.buffer_before, t + self.need + self.project.buffer_after)
        return not any(u in self.occupied for u in zone)

    def admin_state(self, t):
        """設定画面での表示。open：◯（受付中）、closed：×（受付停止）、
        予約が入っている枠は予約のステータス（reserved・done・paid・no_show・test）、
        none：-（締め切った枠・募集期間外・予約の前後で閉じた枠。切り替えられない）"""
        r = self.occupied.get(t)
        if r is not None:
            return r.status
        slot = self.slots.get(t)
        if slot is None or t < self.cutoff or not self.project.in_period(t) or t in self.blocked:
            return 'none'
        return 'closed' if slot.closed else 'open'


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


def _week(project, first, times, make_cell, now, exclude=None):
    start = datetime.datetime.combine(first, datetime.time())
    availability = Availability(project, start, start + WEEK, now, exclude)
    columns = _columns(first)
    rows = [
        {'time': f'{t:%-H:%M}',
         'cells': [make_cell(availability, datetime.datetime.combine(c['date'], t)) for c in columns]}
        for t in times
    ]
    last = first + datetime.timedelta(days=6)
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


def user_week(project, first, selected='', now=None, exclude=None):
    times = [t for t in ALL_TIMES if project.time_start <= t < project.time_end]

    def cell(availability, t):
        # 所要時間ぶん予約できる枠だけ◯（押せる）にする。
        # 空いているが、ここからは所要時間ぶんの空きがない枠は薄い◯（押せない）。それ以外は理由にかかわらず「×」
        if not availability.startable(t):
            return {'faint': True} if availability.free(t) else None
        slot = availability.slots[t]
        return {'slot': slot, 'label': slot.label(project.duration), 'checked': str(slot.pk) == selected}

    return _week(project, first, times, cell, now, exclude)


def can_book(project, slot, now=None, exclude=None):
    """この枠から予約できるか（申し込み・日時の変更のときに確かめる）"""
    return Availability(project, slot.start, slot.start + DAY, now, exclude).startable(slot.start)


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
    def cell(availability, t):
        state = availability.admin_state(t)
        return {
            'state': state,
            'mark': STATUS_MARKS.get(state, ''),
            'slot': availability.slots.get(t),
            'reservation': availability.occupied.get(t),
            'label': f'{t.month}月{t.day}日 {t:%-H:%M}',
        }

    return _week(project, first, ALL_TIMES, cell, now)


def toggleable(project, slots, now=None):
    """◯・×を切り替えてよい枠（設定画面で「◯」か「×」と表示している枠）だけを返す"""
    if not slots:
        return []
    starts = [s.start for s in slots]
    availability = Availability(project, min(starts), max(starts) + SLOT, now)
    return [s for s in slots if availability.admin_state(s.start) in ('open', 'closed')]
