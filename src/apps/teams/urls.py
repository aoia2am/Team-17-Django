# src/apps/teams/urls.py
from django.urls import path

from . import views

"""
共同開発ルール:
- modelsとurlsを元に、viewsとformsを実装してください!! 
- エラーが起きないように下記はコメントアウト状態にしています
"""

app_name = "teams"

urlpatterns = [
    # onboarding の「作る」
    path("create/", views.team_create_view, name="create"),

    # onboarding の「参加する」
    path("join/", views.team_join_view, name="join"),

    # チーム情報
    path("<int:team_id>/", views.team_detail_view, name="detail"),

    # 招待コード（再生成/無効化）
    path("<int:team_id>/invite/regenerate/", views.invite_regenerate_view, name="invite_regenerate"),
    path("<int:team_id>/invite/deactivate/", views.invite_deactivate_view, name="invite_deactivate"),
]