# PythonAnywhere の「WSGI configuration file」の中身の雛形。
# 「Web」タブの WSGI configuration file のリンクを開き、中身を全部消してこれを貼り、
# <ユーザー名> と <フォルダ名> を自分のものに書き換える。

import os
import sys

path = '/home/<ユーザー名>/<フォルダ名>'   # 例：/home/yourlab/scheduler
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'django_app.settings'

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
