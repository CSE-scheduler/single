from django.urls import path

from . import setting_views, views

urlpatterns = [
    path('', setting_views.root),

    # ---- 設定画面（実験者用・パスワードで保護） ----
    path('setting/login', setting_views.login, name='setting_login'),
    path('setting/logout', setting_views.logout, name='setting_logout'),
    path('setting/home', setting_views.home, name='setting_home'),
    path('setting/home/<str:project>', setting_views.project_edit, name='setting_project'),
    path('setting/home/<str:project>/appointments', setting_views.appointments, name='setting_appointments'),
    path('setting/home/<str:project>/slots', setting_views.toggle_slots, name='setting_slots'),

    # ---- 参加者用（プロジェクトごと） ----
    path('<str:project>/', views.consent, name='consent'),
    path('<str:project>/manual', views.manual, name='manual'),
    path('<str:project>/timeframe', views.timeframe, name='timeframe'),
    path('<str:project>/entry', views.entry, name='entry'),
    path('<str:project>/confirm', views.confirm, name='confirm'),
    path('<str:project>/complete', views.complete, name='complete'),
]
