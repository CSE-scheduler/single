"""確認メールの送信。予約直後はその場で送り、2日前・前日・1時間前は
manage.py send_reminders（PythonAnywhereの「Tasks」で定期実行）で送る"""

import datetime
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError

from .models import MailLog, Reservation

logger = logging.getLogger(__name__)

# (種類, 設定画面での名前, 実験の何時間前に送るか)。予約直後は None
KINDS = [
    ('booking', '予約直後', None),
    ('2days', '2日前', datetime.timedelta(days=2)),
    ('1day', '前日', datetime.timedelta(days=1)),
    ('1hour', '1時間前', datetime.timedelta(hours=1)),
]
KIND_FIELDS = {'booking': 'mail_on_booking', '2days': 'mail_2days', '1day': 'mail_1day', '1hour': 'mail_1hour'}


def render(project, reservation):
    """件名と本文の {日時} {氏名} を置き換える"""
    values = {
        '{日時}': reservation.slot.label(with_year=True),
        '{氏名}': reservation.full_name,
    }
    subject, body = project.mail_subject, project.mail_body
    for key, value in values.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)
    return subject, body.replace('\r\n', '\n')


def send(reservation, kind):
    """1通送る。すでに送った種類なら送らない。送れたら True"""
    project = reservation.slot.project
    if not reservation.mail:
        return False
    # 先に記録を作り、同時に2回呼ばれても二重に送らないようにする
    try:
        log = MailLog.objects.create(reservation=reservation, kind=kind)
    except IntegrityError:
        return False
    subject, body = render(project, reservation)
    from_email = project.mail_from or settings.DEFAULT_FROM_EMAIL
    message = EmailMessage(
        subject, body, from_email, [reservation.mail],
        reply_to=[project.mail_from] if project.mail_from else None,
    )
    try:
        message.send()
    except Exception:
        # 送れなかったときは記録を消して、次の実行でもう一度送る
        logger.exception('確認メールを送れませんでした（予約 %s、%s）', reservation.pk, kind)
        log.delete()
        return False
    return True


def send_on_booking(reservation):
    project = reservation.slot.project
    if project.mail_enabled and project.mail_on_booking:
        send(reservation, 'booking')


def send_due(now=None):
    """送る時刻を過ぎた（まだ実験が始まっていない）リマインドを送る。送った数を返す"""
    now = now or datetime.datetime.now()
    longest = max(delta for _, _, delta in KINDS if delta)
    reservations = (
        Reservation.objects
        .filter(slot__project__mail_enabled=True, slot__start__gt=now, slot__start__lte=now + longest)
        .exclude(mail='')
        .select_related('slot__project')
        .prefetch_related('mail_logs')
    )
    count = 0
    for reservation in reservations:
        project = reservation.slot.project
        sent = {log.kind for log in reservation.mail_logs.all()}
        for kind, _, delta in KINDS:
            if not delta or kind in sent or not getattr(project, KIND_FIELDS[kind]):
                continue
            due = reservation.slot.start - delta
            # 送る時刻より後に予約した人には送らない（例：前日の夜に予約した人に「2日前」のメールは送らない）
            if due <= now and reservation.created_at <= due:
                count += send(reservation, kind)
    return count
