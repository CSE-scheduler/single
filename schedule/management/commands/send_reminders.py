import datetime
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from schedule.mail import send_due


class Command(BaseCommand):
    help = '送る時刻を過ぎた確認メール（2日前・前日・1時間前）を送る'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop', type=int, default=0, metavar='秒',
            help='終わらずに、この秒数ごとに確かめ続ける（PythonAnywhereの Always-on task 用）',
        )

    def handle(self, *args, loop, **options):
        while True:
            close_old_connections()  # 長く動かし続けても、切れたデータベース接続を使わないように
            count = send_due()
            if count or not loop:
                self.stdout.write(f'{datetime.datetime.now():%Y-%m-%d %H:%M} {count}通送りました')
            if not loop:
                return
            time.sleep(loop)
