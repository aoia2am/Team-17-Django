from django.urls import path
from django.http import HttpResponse

# NOTE:
# - views.py を実装したら、以下のコメントアウトを外す
# - 達成（状態変更）は POST 推奨（views 側で @require_POST を付与）

from . import views

app_name = "quests"

def _todo(_request, *args, **kwargs):
    return HttpResponse("TODO: quests views")

urlpatterns = [
    # 今日のクエスト表示（チーム単位 / 4件）
    #GET
    path("today/", views.today_view, name="today"),

    # クエスト達成（モーダルの Yes → POST）
    #POST
    path("complete/<int:daily_item_id>/", views.complete_view, name="complete"),

    # チーム進捗（星表示など）
    #GET
    path("progress/", views.progress_view, name="progress"),

    # MVP表示（最も稼いだ人 / 同値は最速）
    #GET
    path("mvp/", views.mvp_view, name="mvp"),
]
