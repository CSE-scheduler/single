import secrets

from django.db import migrations, models

import schedule.models


def fill(apps, schema_editor):
    # 謝金支払い済みだった予約は「謝金支払い済み」、それ以外は「予約済み」にする。予約ごとにURL用の文字列を作る
    Reservation = apps.get_model('schedule', 'Reservation')
    for r in Reservation.objects.all():
        r.status = 'paid' if r.paid else 'reserved'
        r.token = secrets.token_urlsafe(16)
        r.save(update_fields=['status', 'token'])


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0005_buffer_enabled'),
    ]

    operations = [
        migrations.RenameField(model_name='project', old_name='mail_bcc', new_name='mail_reply_to'),
        migrations.AlterField(
            model_name='project',
            name='mail_reply_to',
            field=models.EmailField(blank=True, default='', max_length=254, verbose_name='返信用メールアドレス'),
        ),
        migrations.AlterField(
            model_name='project',
            name='mail_body',
            field=models.TextField(blank=True, default=schedule.models.DEFAULT_MAIL_BODY, verbose_name='本文'),
        ),
        migrations.AddField(
            model_name='reservation',
            name='status',
            field=models.CharField(
                choices=schedule.models.RESERVATION_STATUSES, default='reserved', max_length=10, verbose_name='ステータス',
            ),
        ),
        migrations.AddField(
            model_name='reservation',
            name='token',
            field=models.CharField(max_length=32, null=True, editable=False),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
        migrations.RemoveField(model_name='reservation', name='paid'),
        migrations.AlterField(
            model_name='reservation',
            name='token',
            field=models.CharField(default=schedule.models.new_token, editable=False, max_length=32, unique=True),
        ),
    ]
