"""予約のメール。予約が完了したとき・日時を変更したときは予約確認メール、キャンセルしたときはキャンセルのメールを送る。

- 差出人（From）は local_settings.py の送信用Gmail
- 返信先（Reply-To）はプロジェクトの「返信用メールアドレス」。参加者が「返信」を押すと、このアドレス宛てになる
- 「予約メールを自分も受け取る」がオンなら、返信用メールアドレスにもBCCで同じメールを送る（予約の通知の代わり）
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

# 本文・タイトルで置き換える文字
PLACEHOLDERS = ['{日時}', '{氏名}', '{返信用メールアドレス}', '{キャンセル用URL}']


def render(subject, body, project, reservation, manage_url=''):
    """タイトルと本文の {日時} {氏名} {返信用メールアドレス} {キャンセル用URL} を置き換える"""
    values = {
        '{日時}': reservation.label(with_year=True),
        '{氏名}': reservation.full_name,
        '{返信用メールアドレス}': project.mail_reply_to,
        '{キャンセル用URL}': manage_url,
    }
    for key, value in values.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)
    # 改行が入るとメールのタイトルにできないので1行にする
    subject = ' '.join(subject.split())
    return subject, body.replace('\r\n', '\n')


def _send(project, reservation, subject, body):
    reply_to = [project.mail_reply_to] if project.mail_reply_to else None
    bcc = [project.mail_reply_to] if project.mail_reply_to and project.mail_bcc_self else None
    message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [reservation.mail], bcc=bcc, reply_to=reply_to)
    try:
        message.send()
    except Exception:
        logger.exception('予約のメールを送れませんでした（予約 %s）', reservation.pk)
        return False
    return True


def send_confirmation(reservation, manage_url):
    """予約確認メールを送る。送れたら True。manage_url は予約の変更・キャンセルのページのURL"""
    project = reservation.slot.project
    if not project.mail_enabled or not reservation.mail:
        return False
    subject, body = render(project.mail_subject, project.mail_body, project, reservation, manage_url)
    return _send(project, reservation, subject, body)


def send_cancel(reservation):
    """キャンセルのメールを送る（予約を消す前に呼ぶ）。送れたら True"""
    project = reservation.slot.project
    if not project.mail_enabled or not reservation.mail:
        return False
    subject, body = render(project.mail_cancel_subject, project.mail_cancel_body, project, reservation)
    return _send(project, reservation, subject, body)
