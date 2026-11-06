# 日程調整（CSE scheduler）

実験の参加日時を予約してもらうための Django アプリです。プロジェクト（実験）ごとに予約画面・設定を分けられます。

公開先：https://csescheduler.pythonanywhere.com/

## 画面

| URL | 画面 |
| --- | --- |
| `/<プロジェクト名>/` | 参加者用。最初の画面（同意画面）→ 日時選択 → 入力 → 予約完了 |
| `/setting/home` | 設定画面（パスワードが必要）。プロジェクトの作成・一覧・削除 |
| `/setting/home/<プロジェクト名>` | プロジェクトの編集。予約状況カレンダー（マスを押して受付・受付停止を切り替え）、各画面の文言、説明書、取得する項目 |
| `/setting/home/<プロジェクト名>/appointments` | 予約一覧。日時・氏名で並べ替え、期間で絞り込み、謝金支払い済みの切り替え、予約の削除 |

- 枠は 8:00〜23:00 の30分ごと。今日から90日後までの枠が、画面を開いたときに自動で作られます（`schedule/models.py` の `DAYS_AHEAD` などで変えられます）。
- 参加者が予約できるのは明日以降の枠です。
- カレンダーの記号：◯ 受付中／× 受付停止（設定画面で止めた枠）／済 予約あり。

## 手元で動かす

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

`django_app/local_settings.py` がないときは開発用の設定（SQLite、設定画面のパスワード `1234`）で動きます。
http://127.0.0.1:8000/setting/home を開いてプロジェクトを作ってください。

テスト：`.venv/bin/python manage.py test schedule`

## PythonAnywhere へのデプロイ（初回）

アカウント `csescheduler` の「Consoles」から **Bash** を開いて：

```bash
git clone https://github.com/CSE-scheduler/single.git
cd single
mkvirtualenv --python=python3.12 scheduler   # 仮想環境を作る（作ると自動で有効になる）
pip install -r requirements.txt

# 本番の設定ファイルを作り、SECRET_KEY と設定画面のパスワードを書き換える
cp django_app/local_settings_example.py django_app/local_settings.py
python -c "import secrets; print(secrets.token_urlsafe(50))"   # これを SECRET_KEY に貼る
nano django_app/local_settings.py

python manage.py migrate
python manage.py collectstatic --noinput
```

次に「Web」タブで：

1. **Add a new web app** → ドメインは `csescheduler.pythonanywhere.com` → **Manual configuration** → **Python 3.12**
2. **Virtualenv** に `/home/csescheduler/.virtualenvs/scheduler` を入力
3. **Source code** と **Working directory** に `/home/csescheduler/single` を入力
4. **WSGI configuration file**（`/var/www/csescheduler_pythonanywhere_com_wsgi.py`）を開き、中身を全部消して次の内容にする

   ```python
   import os
   import sys

   path = '/home/csescheduler/single'
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'django_app.settings'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

5. **Static files** に URL `/static/`、Directory `/home/csescheduler/single/staticfiles` を追加
6. **Force HTTPS** をオンにする
7. 上の緑の **Reload** ボタンを押す

https://csescheduler.pythonanywhere.com/setting/home を開き、`local_settings.py` に書いたパスワードでログインできれば完了です。

### MySQL を使うとき（任意）

標準では SQLite（`db.sqlite3`）に保存します。MySQL にするときは：「Databases」タブで MySQL のパスワードを決めてから、`requirements.txt` の `mysqlclient` の行の `#` を外して `pip install -r requirements.txt`、`local_settings.py` の `MYSQL = {...}` のコメントを外して値を書き、`python manage.py migrate` → Reload。

## 更新するとき

手元で変更を GitHub に push したあと、PythonAnywhere の Bash で：

```bash
cd ~/single
workon scheduler
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```

最後に「Web」タブで **Reload** を押します。
