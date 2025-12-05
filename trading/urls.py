from django.urls import path

from .views import okx_webhook, health_check, discord_check, webhook_test, webhook_logs

urlpatterns = [
    path("okx/", okx_webhook, name="okx-webhook"),
    path("health/", health_check, name="health-check"),
    path("discord-check/", discord_check, name="discord-check"),
    path("test/", webhook_test, name="webhook-test"),
    path("logs/", webhook_logs, name="webhook-logs"),
]


