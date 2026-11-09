"""設定画面のパスワードを決めて、local_settings.py に書く1行を表示する。

    python manage.py make_admin_password

パスワードは画面に表示されず、シェルの履歴にも残らない。
"""

from getpass import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '設定画面のパスワードを決めて、local_settings.py に書く SCHEDULE_ADMIN_PASSWORD_HASH の行を表示します。'

    def handle(self, *args, **options):
        password = getpass('設定画面のパスワード: ')
        if len(password) < 8:
            raise CommandError('パスワードは8文字以上にしてください。')
        if getpass('もう一度: ') != password:
            raise CommandError('2回の入力が一致しません。')
        self.stdout.write('\n次の1行を django_app/local_settings.py に書いて、Webアプリを再読み込みしてください：\n')
        self.stdout.write(f'SCHEDULE_ADMIN_PASSWORD_HASH = "{make_password(password)}"\n')
