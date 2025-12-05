from django.urls import path

from .views import okx_webhook

urlpatterns = [
    path("okx/", okx_webhook, name="okx-webhook"),
]


