from django.urls import path

from .views import binance_webhook, binance_health_check, binance_account_check

urlpatterns = [
    # APPEND_SLASH=False 설정에서 슬래시 있는 버전과 없는 버전 모두 지원
    path("binance", binance_webhook, name="binance-webhook"),
    path("binance/", binance_webhook, name="binance-webhook-slash"),
    path("binance/health/", binance_health_check, name="binance-health-check"),
    path("binance/account-check/", binance_account_check, name="binance-account-check"),
]

