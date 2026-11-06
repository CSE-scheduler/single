"""予約確認メール。予約が完了したときに送る"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def render(project, reservation):
    """タイトルと本文の {日時} {氏名} を置き換える"""
    values = {
        '{日時}': reservation.label(with_year=True),
        '{氏名}': reservation.full_name,
    }
    subject, body = project.mail_subject, project.mail_body
    for key, value in values.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)
    # 改行が入るとメールのタイトルにできないので1行にする
    subject = ' '.join(subject.split())
    return subject, body.replace('\r\n', '\n')


def send_confirmation(reservation):
    """予約確認メールを送る。送れたら True"""
    project = reservation.slot.project
    if not project.mail_enabled or not reservation.mail:
        return False
    subject, body = render(project, reservation)
    message = EmailMessage(
        subject, body, settings.DEFAULT_FROM_EMAIL, [reservation.mail],
        bcc=[project.mail_bcc] if project.mail_bcc else None,
    )
    try:
        message.send()
    except Exception:
        logger.exception('予約確認メールを送れませんでした（予約 %s）', reservation.pk)
        return False
    return True
