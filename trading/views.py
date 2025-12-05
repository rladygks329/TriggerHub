import json
import os
from typing import Any, Dict

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .okx_client import OkxClient


def _get_okx_client() -> OkxClient:
    return OkxClient(
        api_key=os.environ["OKX_API_KEY"],
        secret_key=os.environ["OKX_SECRET_KEY"],
        passphrase=os.environ["OKX_PASSPHRASE"],
    )


def _parse_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    트레이딩뷰 Webhook 등에서 들어오는 payload를 내부 포맷으로 변환하는 자리.
    일단은 최소 필드만 가정해서 사용.
    """
    symbol = payload.get("symbol") or payload.get("instId")
    side = payload.get("side") or payload.get("action")
    size = payload.get("size") or payload.get("qty") or "1"
    if not symbol or side not in ("buy", "sell"):
        raise ValueError("invalid payload: symbol/side 부족")
    return {"symbol": symbol, "side": side, "size": str(size)}


@csrf_exempt  # 외부 Webhook이기 때문에 CSRF 예외; 필요시 시크릿 토큰 검증 추가
@require_POST
def okx_webhook(request: HttpRequest):
    try:
        raw = request.body.decode("utf-8") or "{}"
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    # 선택: 간단한 시크릿 키 검증 (TradingView에서 함께 보내도록 설정)
    secret = os.getenv("WEBHOOK_SECRET")
    if secret:
        if payload.get("secret") != secret:
            return JsonResponse({"ok": False, "error": "invalid_secret"}, status=403)

    try:
        signal = _parse_signal(payload)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    client = _get_okx_client()
    try:
        resp = client.place_market_order(
            inst_id=signal["symbol"],
            side=signal["side"],
            sz=signal["size"],
        )
        # 간단한 콘솔 로그
        print("[OKX ORDER] symbol=%s side=%s size=%s resp=%s" % (signal["symbol"], signal["side"], signal["size"], resp))

        # OKX 응답 포맷에 맞게 orderId 추출 (간략화)
        data = resp.get("data") or []
        order_id = data[0].get("ordId") if data else None
        return JsonResponse({"ok": True, "order_id": order_id})
    except Exception as e:  # 실제로는 더 구체적인 예외 처리 권장
        raw_resp = None
        if hasattr(e, "response") and getattr(e, "response") is not None:
            try:
                raw_resp = e.response.text
            except Exception:
                raw_resp = "unavailable"
        print("[OKX ORDER ERROR]", e, "raw_response:", raw_resp)
        return JsonResponse({"ok": False, "error": str(e), "raw_response": raw_resp}, status=500)


