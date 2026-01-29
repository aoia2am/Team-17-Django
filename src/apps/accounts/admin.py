# src/apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    運営・デバッグ用の User 管理画面。

    NOTE:
    - 一般ユーザーは基本ここを触らない
    - Hackathonでは「状態確認できる」ことを最優先
    """

    model = User

    # 一覧で見たい項目
    list_display = (
        "email",
        "display_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
    )

    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "display_name")
    ordering = ("-created_at",)

    # 編集画面
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )
