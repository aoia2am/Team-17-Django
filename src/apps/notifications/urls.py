# src/apps/notifications/urls.py
from django.urls import path

# NOTE:
# - views.py を実装したら、以下のコメントアウトを外す
# - 破壊的/状態変更（既読化）は POST 推奨（views 側で @require_POST を付与）

# from . import views

app_name = "notifications"

urlpatterns = [
    # チーム通知フィード（チーム内タイムライン）
    # GET: 一覧表示
    # path("team/<int:team_id>/", views.notification_list_view, name="list"),

    # 既読化（未読バッジ用）
    # POST: 1件既読
    # path("<int:notification_id>/read/", views.notification_read_view, name="read"),

    # POST: 全件既読（任意：発表映え）
    # path("team/<int:team_id>/read-all/", views.notification_read_all_view, name="read_all"),
]
