"""予約確認メール。予約が完了したとき・日時を変更したときに送る"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def render(project, reservation, manage_url):
    """タイトルと本文の {日時} {氏名} {返信用メールアドレス} {キャンセル用URL} を置き換える"""
    values = {
        '{日時}': reservation.label(with_year=True),
        '{氏名}': reservation.full_name,
        '{返信用メールアドレス}': project.mail_reply_to,
        '{キャンセル用URL}': manage_url,
    }
    subject, body = project.mail_subject, project.mail_body
    for key, value in values.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)
    # 改行が入るとメールのタイトルにできないので1行にする
    subject = ' '.join(subject.split())
    return subject, body.replace('\r\n', '\n')


def send_confirmation(reservation, manage_url):
    """予約確認メールを送る。送れたら True。manage_url は予約の変更・キャンセルのページのURL"""
    project = reservation.slot.project
    if not project.mail_enabled or not reservation.mail:
        return False
    subject, body = render(project, reservation, manage_url)
    message = EmailMessage(
        subject, body, settings.DEFAULT_FROM_EMAIL, [reservation.mail],
        reply_to=[project.mail_reply_to] if project.mail_reply_to else None,
    )
    try:
        message.send()
    except Exception:
        logger.exception('予約確認メールを送れませんでした（予約 %s）', reservation.pk)
        return False
    return True
