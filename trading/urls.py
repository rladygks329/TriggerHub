from django.urls import path

from .views import okx_webhook, health_check

urlpatterns = [
    path("okx/", okx_webhook, name="okx-webhook"),
    path("health/", health_check, name="health-check"),
]


