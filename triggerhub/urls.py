from django.contrib import admin
from django.urls import path, include

# 에러 핸들러 등록
handler400 = "triggerhub.error_handlers.handler400"
handler403 = "triggerhub.error_handlers.handler403"
handler404 = "triggerhub.error_handlers.handler404"
handler500 = "triggerhub.error_handlers.handler500"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("webhook/", include("trading.urls")),
    path("webhook/", include("binance.urls")),
]


