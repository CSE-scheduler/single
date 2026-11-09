# 設置ガイド（自分たちのサーバーで使う）

このアプリを自分の研究室のサーバー・メールアドレスで動かすための手順です。
サーバーごとの設定は `django_app/local_settings.py` という1つのファイルにまとめて書きます。プログラム本体は書き換えずに使えます。

- [準備するもの](#準備するもの)
- [設定ファイル（local_settings.py）](#設定ファイルlocal_settingspy)
- [A. PythonAnywhere に置く](#a-pythonanywhere-に置く)（サーバーの知識があまりなくても設置できます）
- [B. 自分の Linux サーバーに置く](#b-自分の-linux-サーバーに置く)（gunicorn + nginx）
- [設置したら確認すること](#設置したら確認すること)
- [更新・バックアップ・引っ越し](#更新バックアップ引っ越し)
- [うまく動かないとき](#うまく動かないとき)

---

## 準備するもの

| もの | 内容 |
| --- | --- |
| サーバー | Python 3.10 以上が動くところ。[PythonAnywhere](https://www.pythonanywhere.com/)（無料プランあり）か、研究室・大学の Linux サーバー |
| メールアカウント | 予約確認メールを送るとき。送信専用の Gmail アカウント（アプリパスワードを使う）か、大学・研究室のメールサーバー |
| ドメイン | PythonAnywhere なら `ユーザー名.pythonanywhere.com` が使える。自分のサーバーなら DNS の設定と HTTPS の証明書 |

参加者の個人情報（氏名・メールアドレスなど）を保存するので、サーバーの場所や管理について所属機関の決まりがあれば確認してください。

---

## 設定ファイル（local_settings.py）

雛形 `django_app/local_settings_example.py` をコピーして作ります。

```bash
cp django_app/local_settings_example.py django_app/local_settings.py
```

`local_settings.py` にはパスワードが入るので、GitHub には上げません（`.gitignore` に登録済み）。書かなかった項目は `django_app/settings.py` の初期値が使われます。

### 必須の項目

| 項目 | 書くこと |
| --- | --- |
| `DEBUG` | `False` |
| `SECRET_KEY` | ランダムな長い文字列。`python -c "import secrets; print(secrets.token_urlsafe(50))"` で作る |
| `ALLOWED_HOSTS` | 公開するドメイン。例：`["yourlab.pythonanywhere.com"]` |
| `SCHEDULE_ADMIN_PASSWORD_HASH` | 設定画面のパスワード。下の「設定画面のパスワード」を参照 |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | HTTPS で公開するなら `True` |

### 設定画面のパスワード

パスワードはそのまま書かず、ハッシュにした値を書きます。サーバーで次を実行し、パスワードを2回入力します。

```bash
python manage.py make_admin_password
```

表示された `SCHEDULE_ADMIN_PASSWORD_HASH = "pbkdf2_sha256$..."` の1行を `local_settings.py` に貼り、Web アプリを再起動します。パスワードを変えるときも同じ手順です。
この行を書いていないあいだは、ログイン画面に「パスワードが設定されていません」と出てログインできません。参加者用の画面はそのまま使えます。

### メール

書かなければメールは送りません（予約はできます）。設定画面の「予約確認メール」に赤字で注意が出ます。

**Gmail を使う場合**（おすすめ：送信専用のアカウントを作る）

1. Google アカウントで2段階認証をオンにする
2. 「アプリパスワード」（16文字）を作る
3. `local_settings.py` に書く

```python
EMAIL_HOST_USER = "your-address@gmail.com"
EMAIL_HOST_PASSWORD = "abcdabcdabcdabcd"   # アプリパスワード（空白は詰める）
```

- アプリパスワードに有効期限はありません。ただし、アカウントのパスワードを変えたり、2段階認証をオフにしたりすると無効になります。送信専用アカウントのパスワードは変えないでください。
- 差出人に名前をつけるなら `DEFAULT_FROM_EMAIL = '"○○研究室 実験予約" <your-address@gmail.com>'`。Gmail では、アドレスを `EMAIL_HOST_USER` と同じにします。
- Gmail には1日に送れる通数の上限があります（個人アカウントで数百通程度）。

**大学・研究室のメールサーバーを使う場合**：値はメールサーバーの管理者に確認してください。

```python
EMAIL_HOST = "smtp.example.ac.jp"
EMAIL_PORT = 587          # STARTTLS なら 587、SSL なら 465
EMAIL_USE_TLS = True      # 587 のとき True
EMAIL_USE_SSL = False     # 465 のとき True（EMAIL_USE_TLS は False に）
EMAIL_HOST_USER = "your-address@example.ac.jp"
EMAIL_HOST_PASSWORD = "パスワード"
# パスワードのいらない学内のサーバーで、EMAIL_HOST_PASSWORD を書かないときは：
# SEND_EMAIL = True
```

サーバーによっては、外部へのメール送信（ポート 587・465）が止められていることがあります。

### データベース

| 使うもの | 書くこと |
| --- | --- |
| SQLite（初期値） | 何も書かない。プロジェクトのフォルダの `db.sqlite3` に保存される。1研究室で使うなら十分 |
| MySQL | `MYSQL = {"NAME": ..., "USER": ..., "PASSWORD": ..., "HOST": ...}`。`requirements.txt` の `mysqlclient` の行を有効にする |
| PostgreSQL など | `DATABASES = {...}` を直接書く。`requirements.txt` の `psycopg` の行を有効にする |

再起動するとファイルが消えるサーバー（一部のクラウドの無料プランなど）では、SQLite は使えません（予約がすべて消えます）。

### 見た目（任意）

左上のロゴと favicon は、プログラムを書き換えずに差し替えられます。

1. プロジェクトのフォルダに `site_static/` を作り、画像を置く（このフォルダは GitHub に上げない）
   - ロゴ：横長の画像（高さ 28px で表示、PNG・SVG など）
   - favicon：正方形の画像（PNG）
2. `local_settings.py` に書く

   ```python
   SITE_NAME = "○○ Lab Scheduler"   # 画像が読めないとき・読み上げのときの文字
   SITE_LOGO = "logo.png"           # site_static/logo.png
   SITE_FAVICON = "favicon.png"     # site_static/favicon.png
   ```

3. `python manage.py collectstatic --noinput` を実行して、Web アプリを再起動する

日本以外で使うときは、`TIME_ZONE`（初期値 `"Asia/Tokyo"`）も書き換えます。枠の時刻はこのタイムゾーンで扱います。

---

## A. PythonAnywhere に置く

以下の `<ユーザー名>` は PythonAnywhere のユーザー名、`scheduler` はプロジェクトを置くフォルダ名です。

### 1. ダウンロードとインストール

「Consoles」タブから **Bash** を開いて：

```bash
git clone <このリポジトリのURL> scheduler
cd scheduler
mkvirtualenv --python=python3.12 scheduler   # 仮想環境を作る（作ると自動で有効になる）
pip install -r requirements.txt
```

### 2. 設定ファイル

```bash
cp django_app/local_settings_example.py django_app/local_settings.py
python -c "import secrets; print(secrets.token_urlsafe(50))"   # SECRET_KEY に貼る
python manage.py make_admin_password                           # 表示された1行を貼る
nano django_app/local_settings.py
```

`ALLOWED_HOSTS` は `["<ユーザー名>.pythonanywhere.com"]` にします。メールの設定も、ここで書きます。
nano では `Ctrl + O` → `Enter` で保存、`Ctrl + X` で終了です。

### 3. データベースと静的ファイル

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

### 4. Web アプリを作る

「Web」タブで：

1. **Add a new web app** → ドメインはそのまま → **Manual configuration** → **Python 3.12**
2. **Virtualenv**：`/home/<ユーザー名>/.virtualenvs/scheduler`
3. **Source code** と **Working directory**：`/home/<ユーザー名>/scheduler`
4. **WSGI configuration file** のリンクを開き、中身を全部消して `deploy/pythonanywhere_wsgi.py` の内容を貼り、`<ユーザー名>` と `<フォルダ名>` を書き換えて保存
5. **Static files** に URL `/static/`、Directory `/home/<ユーザー名>/scheduler/staticfiles` を追加
6. **Force HTTPS** をオンにする
7. 上の緑の **Reload** ボタンを押す

`https://<ユーザー名>.pythonanywhere.com/setting/home` を開き、設定画面のパスワードでログインできれば完了です。

- 無料プランでは、3か月に1回ほど「Web」タブで延長のボタンを押さないと、Web アプリが止まります（届くメールで案内されます）。
- エラーのときは「Web」タブの **Error log** を見ます。

---

## B. 自分の Linux サーバーに置く

Ubuntu などで、gunicorn（アプリを動かす）と nginx（HTTPS と静的ファイルを受け持つ）を使う例です。プロジェクトを `/srv/scheduler` に置くとします。

### 1. ダウンロードとインストール

```bash
sudo mkdir -p /srv/scheduler && sudo chown $USER /srv/scheduler
git clone <このリポジトリのURL> /srv/scheduler
cd /srv/scheduler
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
```

### 2. 設定ファイル

```bash
cp django_app/local_settings_example.py django_app/local_settings.py
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"
.venv/bin/python manage.py make_admin_password
nano django_app/local_settings.py
```

nginx の後ろで動かすので、`SECURE_PROXY_SSL_HEADER` の行の `#` を外します。外さないと、確認メールの URL が `http://` になったり、設定の保存がエラー（403）になったりします。

### 3. データベースと静的ファイル

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
```

SQLite を使う場合は、gunicorn を動かすユーザーが `db.sqlite3` とそのフォルダに書き込めるようにしてください。

### 4. gunicorn と nginx

- `deploy/gunicorn.service`：アプリを動かし続ける systemd の設定。ファイルの先頭に手順があります。
- `deploy/nginx.conf`：nginx の設定。ドメインとフォルダを書き換え、certbot などで HTTPS の証明書を取ります。

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/scheduler.service   # 書き換えてから
sudo systemctl daemon-reload && sudo systemctl enable --now scheduler
sudo cp deploy/nginx.conf /etc/nginx/sites-available/scheduler          # 書き換えてから
sudo ln -s /etc/nginx/sites-available/scheduler /etc/nginx/sites-enabled/
sudo certbot --nginx -d schedule.example.ac.jp
sudo nginx -t && sudo systemctl reload nginx
```

---

## 設置したら確認すること

1. `https://<ドメイン>/setting/home` でログインできる
2. テスト用のプロジェクトを作り、「予約確認メール」に赤字の注意が出ていない（メールを設定した場合）
3. 予約確認メールをオンにし、自分のメールアドレスで予約してみる
   - 確認メールが届く（迷惑メールフォルダも見る）
   - メールの「予約の変更・キャンセル」の URL が `https://` で始まり、開ける
   - 返信すると、返信用メールアドレス宛てになる
4. 予約一覧に出て、キャンセルするとキャンセルのメールが届く
5. 確認が終わったら、テスト用のプロジェクトを削除する

---

## 更新・バックアップ・引っ越し

### 更新

新しい版が出たら、サーバーで：

```bash
cd <プロジェクトのフォルダ>
git pull
pip install -r requirements.txt          # 自分のサーバーなら .venv/bin/pip
python manage.py migrate
python manage.py collectstatic --noinput
```

最後に Web アプリを再起動します（PythonAnywhere は Reload、自分のサーバーは `sudo systemctl restart scheduler`）。
`local_settings.py`・`db.sqlite3`・`site_static/` は GitHub で管理していないので、更新しても上書きされません。

### バックアップ

予約・設定・説明書は、すべてデータベースに入っています。SQLite なら `db.sqlite3` の1ファイルです。

- `sh deploy/backup_sqlite.sh` で、予約を受け付けたまま `backups/` にコピーを取れます（30日より古いものは消します）。
- 毎日自動で取るなら、cron（PythonAnywhere なら「Tasks」タブ）に登録します。
- 個人情報が入っているので、置き場所と保存期間に気をつけてください。

### 別のサーバーへの引っ越し

1. 新しいサーバーに設置し、空のデータベースで動作を確認する
2. 古いサーバーで、各プロジェクトを「停止する」にする（引っ越しのあいだに予約が入らないように）
3. `db.sqlite3` を `scp` などで新しいサーバーにコピーし、`python manage.py migrate` を実行する
4. プロジェクトを「公開する」に戻し、告知に載せた募集ページの URL を差し替える

**すでに送った確認メールの「予約の変更・キャンセル」の URL は、古いドメインのままです。** しばらくは古いドメインから新しいドメインへ転送するか、予約している人に連絡方法を案内してください。

---

## うまく動かないとき

| 症状 | 原因と対処 |
| --- | --- |
| すべてのページが「Bad Request (400)」 | `ALLOWED_HOSTS` にドメインが入っていない |
| 「local_settings.py に SECRET_KEY を設定してください」 | `SECRET_KEY` を書いていない |
| ログイン画面に「パスワードが設定されていません」 | `make_admin_password` で作った行を書いていない。書いたら再起動する |
| ログインしても戻されてしまう | HTTPS でないのに `SESSION_COOKIE_SECURE = True`。HTTPS で開くか、nginx なら `SECURE_PROXY_SSL_HEADER` を書く |
| 設定を保存すると 403 | nginx の後ろで `SECURE_PROXY_SSL_HEADER` を書いていない |
| 見た目が崩れる（CSS が効かない） | `collectstatic` をしていないか、Web サーバーで `/static/` を `staticfiles/` に割り当てていない |
| メールが届かない | 編集画面の「予約確認メールを送る」がオンか、赤字の注意が出ていないかを確認。迷惑メールフォルダも見る。エラーログに「予約のメールを送れませんでした」があれば、メールの設定（アドレス・パスワード・サーバー・ポート）を見直す |
| メールの URL が `http://` になる | nginx の後ろで `SECURE_PROXY_SSL_HEADER` を書いていない |
| 「database is locked」 | SQLite のファイルやフォルダに書き込めないか、ネットワークドライブに置いている |
