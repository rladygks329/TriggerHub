import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .config import get_config
from .okx_client import OkxClient


# ============================================
# 파일 로깅 설정
# ============================================
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 웹훅 로그 파일
WEBHOOK_LOG_FILE = LOG_DIR / "webhook.log"

# 로거 설정
webhook_logger = logging.getLogger("webhook")
webhook_logger.setLevel(logging.INFO)

# 파일 핸들러 (append 모드)
file_handler = logging.FileHandler(WEBHOOK_LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.INFO)

# 포맷 설정
formatter = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(formatter)

# 핸들러 추가 (중복 방지)
if not webhook_logger.handlers:
    webhook_logger.addHandler(file_handler)


def log_webhook(log_type: str, message: str, data: dict = None):
    """웹훅 로그를 파일과 콘솔에 기록"""
    log_line = f"[{log_type}] {message}"
    if data:
        log_line += f" | {json.dumps(data, ensure_ascii=False)}"
    
    # 파일에 기록
    webhook_logger.info(log_line)
    
    # 콘솔에도 출력
    print(log_line)


# 웹훅 테스트 로그 저장 (메모리)
_webhook_logs: list = []
MAX_LOGS = 100  # 최대 로그 개수


def _get_okx_client() -> OkxClient:
    """config.json 설정에서 OKX 클라이언트 생성"""
    return OkxClient.from_config()


def _parse_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    트레이딩뷰 Webhook 등에서 들어오는 payload를 내부 포맷으로 변환.
    config.json의 기본값을 사용하고, payload에서 오버라이드 가능.
    
    지원 필드:
    - symbol / instId: 거래 심볼 (기본값: config.trading.symbol)
    - side / action: buy 또는 sell (필수)
    - size / qty / sz: 주문 수량 (기본값: 1, use_full_balance=true면 자동 계산)
    - tp: Take Profit 퍼센트 (기본값: config.trading.take_profit_percent)
    - sl: Stop Loss 퍼센트 (기본값: config.trading.stop_loss_percent)
    - use_tp_sl: TP/SL 사용 여부 (기본값: true)
    - leverage / lever: 레버리지 배수 (기본값: config.trading.leverage)
    - td_mode / mgnMode: 마진 모드 (기본값: config.trading.td_mode)
    - use_full_balance: 전체 잔고 사용 여부 (기본값: config.trading.use_full_balance)
    """
    config = get_config()
    
    # 필수 필드 파싱 (symbol은 config에서 기본값 제공)
    symbol = payload.get("symbol") or payload.get("instId") or config.trading_symbol
    side = payload.get("side") or payload.get("action")
    
    if not symbol:
        raise ValueError("invalid payload: symbol 부족")
    if side not in ("buy", "sell"):
        raise ValueError("invalid payload: side는 'buy' 또는 'sell'이어야 합니다")
    
    # 레버리지 & 마진 모드 (config 기본값 사용)
    leverage = payload.get("leverage") or payload.get("lever")
    if leverage is not None:
        leverage = int(leverage)
    else:
        leverage = config.trading_leverage
    
    td_mode = payload.get("td_mode") or payload.get("mgnMode") or config.trading_td_mode
    
    # use_full_balance 설정
    use_full_balance = payload.get("use_full_balance")
    if use_full_balance is None:
        use_full_balance = config.use_full_balance
    elif isinstance(use_full_balance, str):
        use_full_balance = use_full_balance.lower() not in ("false", "0", "no")
    
    # 수량 결정: use_full_balance=true면 "auto", 아니면 payload 또는 기본값 "1"
    if use_full_balance:
        size = "auto"  # 나중에 실제 수량 계산
    else:
        size = payload.get("size") or payload.get("qty") or payload.get("sz") or "1"
    
    # TP/SL 설정 파싱 (config 기본값 사용)
    use_tp_sl = payload.get("use_tp_sl", True)
    if isinstance(use_tp_sl, str):
        use_tp_sl = use_tp_sl.lower() not in ("false", "0", "no")
    
    tp_percent: Optional[float] = None
    sl_percent: Optional[float] = None
    
    if use_tp_sl:
        tp_value = payload.get("tp")
        sl_value = payload.get("sl")
        
        tp_percent = float(tp_value) if tp_value is not None else config.take_profit_percent
        sl_percent = float(sl_value) if sl_value is not None else config.stop_loss_percent
    
    return {
        "symbol": symbol,
        "side": side,
        "size": str(size),
        "tp_percent": tp_percent,
        "sl_percent": sl_percent,
        "leverage": leverage,
        "td_mode": td_mode,
        "use_full_balance": use_full_balance,
    }


@csrf_exempt  # 외부 Webhook이기 때문에 CSRF 예외
@require_POST
def okx_webhook(request: HttpRequest):
    """
    OKX 자동매매 웹훅 엔드포인트.
    
    POST /webhook/okx/
    
    설정은 config.json에서 읽어오며, payload에서 오버라이드 가능.
    
    요청 예시 (최소):
    {
        "side": "buy"
    }
    
    요청 예시 (전체):
    {
        "secret": "your-webhook-secret",
        "symbol": "BTC-USDT-SWAP",
        "side": "buy",
        "size": "1",
        "tp": 2.3,
        "sl": 0.7,
        "leverage": 10,
        "td_mode": "cross"
    }
    """
    config = get_config()
    
    # 트레이딩 활성화 확인
    if not config.enable_trading:
        return JsonResponse({
            "ok": False,
            "error": "trading_disabled",
            "message": "config.json에서 enable_trading이 false입니다"
        }, status=403)
    
    # JSON 파싱
    try:
        raw = request.body.decode("utf-8") or "{}"
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    # 시크릿 키 검증 (설정된 경우)
    if config.webhook_secret:
        if payload.get("secret") != config.webhook_secret:
            return JsonResponse({"ok": False, "error": "invalid_secret"}, status=403)

    # 신호 파싱
    try:
        signal = _parse_signal(payload)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    # OKX 클라이언트 생성
    client = _get_okx_client()
    
    try:
        # 수량 결정: use_full_balance=true면 자동 계산
        if signal["use_full_balance"] or signal["size"] == "auto":
            calculated_size = client.calculate_order_size(
                inst_id=signal["symbol"],
                leverage=signal["leverage"],
                balance_percent=100.0,  # 100% 사용
            )
            signal["size"] = calculated_size
            print(f"[OKX] 전체 잔고 사용: 계산된 수량 = {calculated_size}")
        
        # 레버리지 설정 후 TP/SL 포함 주문 실행
        resp = client.place_order_with_leverage(
            inst_id=signal["symbol"],
            side=signal["side"],
            sz=signal["size"],
            leverage=signal["leverage"],
            tp_percent=signal["tp_percent"],
            sl_percent=signal["sl_percent"],
            td_mode=signal["td_mode"],
        )
        
        # 응답 처리
        if client.is_success(resp):
            order_id = client.get_order_id(resp)
            
            # 파일 로그 (성공)
            log_webhook("ORDER_SUCCESS", f"symbol={signal['symbol']} side={signal['side']}", {
                "order_id": order_id,
                "size": signal["size"],
                "leverage": signal["leverage"],
                "td_mode": signal["td_mode"],
                "tp_percent": signal["tp_percent"],
                "sl_percent": signal["sl_percent"],
            })
            
            return JsonResponse({
                "ok": True,
                "order_id": order_id,
                "symbol": signal["symbol"],
                "side": signal["side"],
                "size": signal["size"],
                "leverage": signal["leverage"],
                "td_mode": signal["td_mode"],
                "tp_percent": signal["tp_percent"],
                "sl_percent": signal["sl_percent"],
            })
        else:
            error_msg = client.get_error_message(resp)
            
            # 파일 로그 (실패)
            log_webhook("ORDER_FAILED", f"symbol={signal['symbol']}", {
                "error": error_msg,
                "code": resp.get("code"),
            })
            
            return JsonResponse({
                "ok": False,
                "error": error_msg,
                "code": resp.get("code"),
                "raw_response": resp,
            }, status=400)
            
    except Exception as e:
        raw_resp = None
        if hasattr(e, "response") and getattr(e, "response") is not None:
            try:
                raw_resp = e.response.text
            except Exception:
                raw_resp = "unavailable"
        
        # 파일 로그 (예외)
        log_webhook("ORDER_EXCEPTION", str(e), {
            "signal": signal,
            "raw_response": raw_resp,
        })
        
        return JsonResponse({
            "ok": False,
            "error": str(e),
            "raw_response": raw_resp
        }, status=500)


@csrf_exempt
def health_check(request: HttpRequest):
    """
    헬스 체크 엔드포인트.
    서버 상태 및 설정 확인용.
    
    GET /webhook/health/
    """
    config = get_config()
    
    return JsonResponse({
        "ok": True,
        "status": "healthy",
        "trading_enabled": config.enable_trading,
        "default_symbol": config.trading_symbol,
        "default_leverage": config.trading_leverage,
        "default_td_mode": config.trading_td_mode,
        "default_tp_percent": config.take_profit_percent,
        "default_sl_percent": config.stop_loss_percent,
        "is_demo": config.is_demo,
    })


@csrf_exempt
@require_POST
def webhook_test(request: HttpRequest):
    """
    웹훅 테스트 엔드포인트 (실제 주문 없이 로그만 기록).
    TradingView에서 웹훅이 제대로 오는지 확인용.
    
    POST /webhook/test/
    
    - 실제 OKX 주문을 실행하지 않음
    - 받은 데이터를 서버 로그에 출력
    - 메모리에 최근 100개 로그 저장
    """
    global _webhook_logs
    
    # 요청 정보 수집
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    content_type = request.META.get('CONTENT_TYPE', 'unknown')
    
    # Raw body
    try:
        raw_body = request.body.decode("utf-8")
    except Exception:
        raw_body = "<decode error>"
    
    # JSON 파싱 시도
    try:
        payload = json.loads(raw_body) if raw_body else {}
        json_valid = True
    except json.JSONDecodeError as e:
        payload = {"_parse_error": str(e)}
        json_valid = False
    
    # 로그 항목 생성
    log_entry = {
        "timestamp": timestamp,
        "client_ip": client_ip,
        "user_agent": user_agent[:100],  # 길이 제한
        "content_type": content_type,
        "raw_body": raw_body[:1000],  # 길이 제한
        "json_valid": json_valid,
        "payload": payload,
    }
    
    # 메모리에 저장 (최대 100개)
    _webhook_logs.insert(0, log_entry)
    if len(_webhook_logs) > MAX_LOGS:
        _webhook_logs = _webhook_logs[:MAX_LOGS]
    
    # 신호 파싱 시도 (실제 주문 없이)
    parsed_signal = None
    parse_error = None
    
    if json_valid and payload:
        try:
            parsed_signal = _parse_signal(payload)
        except ValueError as e:
            parse_error = str(e)
    
    # 파일 로그 기록 (tail -f 용)
    log_webhook("TEST", f"IP={client_ip}", {
        "json_valid": json_valid,
        "payload": payload,
        "parsed_signal": parsed_signal,
        "parse_error": parse_error,
    })
    
    # 콘솔 로그 출력 (서버 터미널에서 확인)
    print("\n" + "=" * 60)
    print("📥 [WEBHOOK TEST] 웹훅 수신!")
    print("=" * 60)
    print(f"⏰ 시간: {timestamp}")
    print(f"🌐 IP: {client_ip}")
    print(f"📱 User-Agent: {user_agent[:50]}...")
    print(f"📋 Content-Type: {content_type}")
    print(f"✅ JSON 유효: {json_valid}")
    print("-" * 60)
    print("📦 Raw Body:")
    print(raw_body[:500])
    print("-" * 60)
    print("📊 Parsed Payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:500])
    print("=" * 60 + "\n")
    
    # 응답
    return JsonResponse({
        "ok": True,
        "message": "웹훅 테스트 수신 완료 (실제 주문 없음)",
        "received_at": timestamp,
        "client_ip": client_ip,
        "json_valid": json_valid,
        "payload": payload,
        "parsed_signal": parsed_signal,
        "parse_error": parse_error,
    })


@csrf_exempt
def webhook_logs(request: HttpRequest):
    """
    웹훅 테스트 로그 조회.
    
    GET /webhook/logs/
    GET /webhook/logs/?limit=10
    GET /webhook/logs/?clear=true
    """
    global _webhook_logs
    
    # 로그 초기화
    if request.GET.get("clear") == "true":
        _webhook_logs = []
        return JsonResponse({
            "ok": True,
            "message": "로그가 초기화되었습니다",
        })
    
    # 개수 제한
    limit = int(request.GET.get("limit", 20))
    logs = _webhook_logs[:limit]
    
    return JsonResponse({
        "ok": True,
        "total_count": len(_webhook_logs),
        "showing": len(logs),
        "logs": logs,
    })
