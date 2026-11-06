import datetime

import jpholiday

from .models import DAY_NAMES, N_SLOTS, SLOT_MINUTES, START_HOUR


def slot_times():
    first = datetime.datetime.combine(datetime.date.today(), datetime.time(START_HOUR))
    return [(first + datetime.timedelta(minutes=SLOT_MINUTES * i)).time() for i in range(N_SLOTS)]


def build_weeks(project, first, last):
    """first〜last の枠を、7日ごとのページ（列＝日、行＝時刻）に分ける。枠がないマスは None"""
    if last < first:
        return []
    slots = project.slots.filter(
        start__gte=datetime.datetime.combine(first, datetime.time()),
        start__lt=datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time()),
    ).select_related('reservation')
    by_key = {(s.start.date(), s.start.time()): s for s in slots}

    days = [first + datetime.timedelta(days=i) for i in range((last - first).days + 1)]
    times = slot_times()
    weeks = []
    for w in range(0, len(days), 7):
        keys = days[w:w + 7]
        columns = []
        for day in keys:
            holiday = jpholiday.is_holiday(day)
            columns.append({
                'date': day,
                'label': f'{day.month}/{day.day}',
                'day_name': DAY_NAMES[day.weekday()] + ('・祝' if holiday else ''),
                'kind': 'holiday' if holiday or day.weekday() == 6 else ('saturday' if day.weekday() == 5 else ''),
            })
        rows = []
        for t in times:
            rows.append({'time': f'{t:%-H:%M}', 'cells': [by_key.get((day, t)) for day in keys]})
        weeks.append({
            'title': f'{keys[0].month}/{keys[0].day}〜{keys[-1].month}/{keys[-1].day}',
            'columns': columns,
            'rows': rows,
        })
    return weeks
