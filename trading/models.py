from django.db import models


class TradeLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    symbol = models.CharField(max_length=50)
    side = models.CharField(max_length=10)  # buy / sell
    size = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    raw_payload = models.JSONField()
    okx_order_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, default="requested")

    class Meta:
        ordering = ["-created_at"]


