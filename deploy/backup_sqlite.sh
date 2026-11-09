#!/bin/sh
# SQLite のデータベース（予約・設定・説明書がすべて入っている）をバックアップする雛形。
# 予約を受け付けているあいだでも、壊れずにコピーできる（sqlite3 の .backup を使う）。
#
#   使い方：sh deploy/backup_sqlite.sh
#   毎日自動で取るなら cron に登録する（例：毎日3時）
#     0 3 * * * cd /srv/scheduler && sh deploy/backup_sqlite.sh
#
#   ※ 参加者の個人情報が入っているので、バックアップの置き場所と保存期間に気をつける。

set -e
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
python -c "import sqlite3; s=sqlite3.connect('db.sqlite3'); d=sqlite3.connect('backups/db-$STAMP.sqlite3'); s.backup(d); d.close(); s.close()"
# 30日より古いバックアップは消す
find backups -name 'db-*.sqlite3' -mtime +30 -delete
echo "backups/db-$STAMP.sqlite3 を作りました"
