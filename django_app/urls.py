from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # 設定画面（setting/...）と各プロジェクトの予約画面（<プロジェクト名>/...）
    path("", include("schedule.urls")),
]
