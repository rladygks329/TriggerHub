from django.urls import path

from .views import okx_webhook, health_check, account_check, discord_check, webhook_test, webhook_logs

urlpatterns = [
    # APPEND_SLASH=False 설정에서 슬래시 있는 버전과 없는 버전 모두 지원
    path("okx", okx_webhook, name="okx-webhook"),
    path("okx/", okx_webhook, name="okx-webhook-slash"),
    path("health/", health_check, name="health-check"),
    path("account-check/", account_check, name="account-check"),
    path("discord-check/", discord_check, name="discord-check"),
    path("test/", webhook_test, name="webhook-test"),
    path("logs/", webhook_logs, name="webhook-logs"),
]


