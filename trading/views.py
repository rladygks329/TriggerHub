import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied

from .config import get_config
from .okx_client import OkxClient
from .discord import get_discord_webhook_url, send_discord_message, send_trade_notification

# 로거 설정 (Django settings.py의 로깅 설정 사용)
logger = logging.getLogger(__name__)


def log_webhook(log_type: str, message: str, data: dict = None):
    """웹훅 로그를 표준 로거로 기록"""
    log_line = f"[{log_type}] {message}"
    if data:
        log_line += f" | {json.dumps(data, ensure_ascii=False)}"
    
    logger.info(log_line)


# 웹훅 테스트 로그 저장 (메모리)
_webhook_logs: list = []
MAX_LOGS = 100  # 최대 로그 개수


def _get_okx_client() -> OkxClient:
    """config.json 설정에서 OKX 클라이언트 생성"""
    return OkxClient.from_config()


def _normalize_symbol(symbol: str) -> str:
    """
    TradingView 형식의 symbol을 OKX 형식으로 변환.
    
    예시:
    - "ETHUSDT" → "ETH-USDT-SWAP"
    - "BTCUSDT" → "BTC-USDT-SWAP"
    - "ETH-USDT-SWAP" → "ETH-USDT-SWAP" (이미 OKX 형식이면 그대로)
    """
    if not symbol:
        return symbol
    
    # 이미 OKX 형식인지 확인 (-SWAP 또는 -FUTURES 포함)
    if "-SWAP" in symbol or "-FUTURES" in symbol or "-SPOT" in symbol:
        return symbol
    
    # TradingView 형식 변환 (예: ETHUSDT → ETH-USDT-SWAP)
    # USDT로 끝나는 경우
    if symbol.endswith("USDT"):
        base = symbol[:-4]  # "ETHUSDT" → "ETH"
        return f"{base}-USDT-SWAP"
    
    # BTC로 끝나는 경우
    if symbol.endswith("BTC"):
        base = symbol[:-3]  # "ETHBTC" → "ETH"
        return f"{base}-BTC-SWAP"
    
    # 변환 실패 시 원본 반환
    return symbol


def _parse_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    트레이딩뷰 Webhook 등에서 들어오는 payload를 내부 포맷으로 변환.
    config.json의 기본값을 사용하고, payload에서 오버라이드 가능.
    
    지원 필드:
    - symbol / instId: 거래 심볼 (TradingView 형식 자동 변환: ETHUSDT → ETH-USDT-SWAP)
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
    raw_symbol = payload.get("symbol") or payload.get("instId") or config.trading_symbol
    side = payload.get("side") or payload.get("action")
    
    if not raw_symbol:
        raise ValueError("invalid payload: symbol 부족")
    
    # Symbol 정규화 (TradingView 형식 → OKX 형식)
    symbol = _normalize_symbol(raw_symbol)
    
    # side/action 검증 및 정규화
    if not side:
        raise ValueError("invalid payload: side/action 부족")
    
    # action을 side로 변환 (lowercase)
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"invalid payload: side는 'buy' 또는 'sell'이어야 합니다 (받은 값: {side})")
    
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
    # 함수 진입 확인 (가장 먼저 실행)
    logger.info("=" * 80)
    logger.info(f"[OKX_WEBHOOK] 함수 호출됨 | path={request.path} | method={request.method}")
    logger.info(f"[OKX_WEBHOOK] Content-Type: {request.META.get('CONTENT_TYPE', 'N/A')}")
    logger.info(f"[OKX_WEBHOOK] Request body length: {len(request.body)}")
    logger.info("=" * 80)
    
    # POST 메서드 확인 (수동 체크)
    if request.method != "POST":
        logger.error(f"[OKX_WEBHOOK] ERROR: Method is {request.method}, not POST")
        return JsonResponse({
            "ok": False,
            "error": "method_not_allowed",
            "message": f"POST 메서드만 허용됩니다. 현재 메서드: {request.method}"
        }, status=405)
    
    config = get_config()
    
    # 트레이딩 활성화 확인
    log_webhook("WEBHOOK_REQUEST", "웹훅 요청 수신", {
        "path": request.path,
        "method": request.method,
        "enable_trading": config.enable_trading,
    })
    
    if not config.enable_trading:
        log_webhook("TRADING_DISABLED", "거래 비활성화 상태", {
            "enable_trading": config.enable_trading,
        })
        # PermissionDenied 예외를 발생시켜 에러 핸들러(handler403)가 Discord 알림을 보내도록 함
        raise PermissionDenied("config.json에서 enable_trading이 false입니다")
    
    # JSON 파싱
    try:
        raw = request.body.decode("utf-8") or "{}"
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    # 시크릿 키 검증 (설정된 경우)
    if config.webhook_secret:
        received_secret = str(payload.get("secret", "")).strip()
        expected_secret = str(config.webhook_secret).strip()
        
        # 디버깅 로그 (실제 값은 마스킹)
        log_webhook("SECRET_CHECK", "시크릿 검증 시도", {
            "received_length": len(received_secret),
            "expected_length": len(expected_secret),
            "received_first4": received_secret[:4] if len(received_secret) >= 4 else received_secret,
            "expected_first4": expected_secret[:4] if len(expected_secret) >= 4 else expected_secret,
            "match": received_secret == expected_secret,
            "received_repr": repr(received_secret),
            "expected_repr": repr(expected_secret),
        })
        
        if received_secret != expected_secret:
            log_webhook("SECRET_MISMATCH", "시크릿 불일치", {
                "received_length": len(received_secret),
                "expected_length": len(expected_secret),
                "received_first4": received_secret[:4] if len(received_secret) >= 4 else received_secret,
                "expected_first4": expected_secret[:4] if len(expected_secret) >= 4 else expected_secret,
            })
            # PermissionDenied 예외를 발생시켜 에러 핸들러(handler403)가 Discord 알림을 보내도록 함
            raise PermissionDenied("웹훅 시크릿이 일치하지 않습니다. config.json의 webhook_secret을 확인하세요.")

    # 신호 파싱
    try:
        signal = _parse_signal(payload)
        # 파싱된 신호 로깅
        log_webhook("SIGNAL_PARSED", f"symbol={signal['symbol']} side={signal['side']}", {
            "original_payload": payload,
            "parsed_signal": signal,
        })
    except ValueError as e:
        log_webhook("SIGNAL_PARSE_ERROR", str(e), {"payload": payload})
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    # 활성 계정 목록 가져오기
    active_accounts = config.get_active_accounts()
    
    if not active_accounts:
        error_msg = "활성화된 거래 계정이 없습니다 (useYn: 'y'인 계정 없음)."
        log_webhook("NO_ACTIVE_ACCOUNTS", error_msg, {"payload": payload})
        return JsonResponse({"ok": False, "error": error_msg}, status=400)
    
    # 모든 활성 계정에 주문 실행
    results = []
    errors = []
    
    for account_config in active_accounts:
        account_name = account_config.get("name", "unknown")
        log_webhook("TRADING_ACCOUNT", f"계정 '{account_name}'으로 주문 시도", {
            "account": account_name,
            "signal": signal
        })
        
        # 계정별 OKX 클라이언트 생성
        client = OkxClient.from_account_config(account_config, config.trading, config)
        
        try:
            # 수량 결정: use_full_balance=true면 자동 계산
            account_signal = signal.copy()
            if account_signal["use_full_balance"] or account_signal["size"] == "auto":
                log_webhook("SIZE_CALCULATION", f"계정 '{account_name}' 전체 잔고 기반 수량 계산 시작", {
                    "symbol": account_signal["symbol"],
                    "leverage": account_signal["leverage"],
                })
                calculated_size = client.calculate_order_size(
                    inst_id=account_signal["symbol"],
                    leverage=account_signal["leverage"],
                    balance_percent=100.0,  # 100% 사용
                )
                account_signal["size"] = calculated_size
                log_webhook("SIZE_CALCULATED", f"계정 '{account_name}' 계산된 수량={calculated_size}", {
                    "symbol": account_signal["symbol"],
                    "size": calculated_size,
                })
            
            # 주문 실행 전 로깅
            log_webhook("ORDER_START", f"계정 '{account_name}' 주문 실행 시작", {
                "account": account_name,
                "symbol": account_signal["symbol"],
                "side": account_signal["side"],
                "size": account_signal["size"],
                "leverage": account_signal["leverage"],
                "td_mode": account_signal["td_mode"],
                "tp_percent": account_signal["tp_percent"],
                "sl_percent": account_signal["sl_percent"],
            })
            
            # 레버리지 설정 후 TP/SL 포함 주문 실행
            resp = client.place_order_with_leverage(
                inst_id=account_signal["symbol"],
                side=account_signal["side"],
                sz=account_signal["size"],
                leverage=account_signal["leverage"],
                tp_percent=account_signal["tp_percent"],
                sl_percent=account_signal["sl_percent"],
                td_mode=account_signal["td_mode"],
            )
            
            # 응답 처리
            if client.is_success(resp):
                order_id = client.get_order_id(resp)
                
                # 파일 로그 (성공)
                log_webhook("ORDER_SUCCESS", f"계정 '{account_name}' symbol={account_signal['symbol']} side={account_signal['side']}", {
                    "account": account_name,
                    "order_id": order_id,
                    "size": account_signal["size"],
                    "leverage": account_signal["leverage"],
                    "td_mode": account_signal["td_mode"],
                    "tp_percent": account_signal["tp_percent"],
                    "sl_percent": account_signal["sl_percent"],
                })
                
                results.append({
                    "account": account_name,
                    "ok": True,
                    "order_id": order_id,
                    "symbol": account_signal["symbol"],
                    "side": account_signal["side"],
                    "size": account_signal["size"],
                    "leverage": account_signal["leverage"],
                    "td_mode": account_signal["td_mode"],
                    "tp_percent": account_signal["tp_percent"],
                    "sl_percent": account_signal["sl_percent"],
                })
            else:
                error_msg = client.get_error_message(resp)
                
                # 파일 로그 (실패)
                log_webhook("ORDER_FAILED", f"계정 '{account_name}' symbol={account_signal['symbol']}", {
                    "account": account_name,
                    "error": error_msg,
                    "code": resp.get("code"),
                })
                
                # Discord 알림 전송 (주문 실패)
                webhook_url = get_discord_webhook_url()
                if webhook_url:
                    try:
                        send_trade_notification(
                            webhook_url=webhook_url,
                            symbol=account_signal["symbol"],
                            side=account_signal["side"],
                            size=account_signal["size"],
                            status="error",
                            error=f"[{account_name}] {error_msg}",
                        )
                    except Exception as e:
                        logger.error(f"Discord 알림 전송 실패 (주문 실패): {e}")
                
                errors.append({
                    "account": account_name,
                    "error": error_msg,
                    "code": resp.get("code"),
                    "raw_response": resp,
                })
                
        except Exception as e:
            raw_resp = None
            if hasattr(e, "response") and getattr(e, "response") is not None:
                try:
                    raw_resp = e.response.text
                except Exception:
                    raw_resp = "unavailable"
            
            error_msg = str(e)
            
            # 파일 로그 (예외)
            log_webhook("ORDER_EXCEPTION", f"계정 '{account_name}' {error_msg}", {
                "account": account_name,
                "signal": account_signal,
                "raw_response": raw_resp,
            })
            
            # Discord 알림 전송 (예외)
            webhook_url = get_discord_webhook_url()
            if webhook_url:
                try:
                    send_trade_notification(
                        webhook_url=webhook_url,
                        symbol=account_signal.get("symbol", "UNKNOWN"),
                        side=account_signal.get("side", "unknown"),
                        size=account_signal.get("size", "0"),
                        status="error",
                        error=f"[{account_name}] {error_msg}",
                    )
                except Exception as discord_error:
                    logger.error(f"Discord 알림 전송 실패 (주문 예외): {discord_error}")
            
            errors.append({
                "account": account_name,
                "error": error_msg,
                "raw_response": raw_resp
            })
    
    # 결과 반환
    if results:
        return JsonResponse({
            "ok": True,
            "total_accounts": len(active_accounts),
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors if errors else None,
        })
    else:
        return JsonResponse({
            "ok": False,
            "error": "모든 계정에서 주문 실패",
            "total_accounts": len(active_accounts),
            "errors": errors,
        }, status=500)


@csrf_exempt
def health_check(request: HttpRequest):
    """
    헬스 체크 엔드포인트.
    서버 상태 확인용.
    
    GET /webhook/health/
    """
    return JsonResponse({
        "ok": True,
        "status": "healthy",
    })


@csrf_exempt
def account_check(request: HttpRequest):
    """
    계정 정보 및 잔고 조회 엔드포인트.
    모든 계정(useYn과 관계없이)의 잔고를 조회합니다.
    
    GET /webhook/account-check/
    """
    config = get_config()
    
    # 모든 계정 목록 (민감 정보 마스킹)
    accounts_info = []
    account_balances = []
    
    for account in config.accounts:
        account_name = account.get("name", "unknown")
        use_yn = account.get("useYn", "n").lower()
        
        # 계정 정보 (민감 정보 마스킹)
        account_copy = account.copy()
        for key in ["api_key", "secret_key", "passphrase"]:
            if key in account_copy and account_copy[key]:
                account_copy[key] = "***" + account_copy[key][-4:] if len(account_copy[key]) > 4 else "****"
        accounts_info.append(account_copy)
        
        # 모든 계정의 잔고 조회 (useYn과 관계없이)
        try:
            client = OkxClient.from_account_config(account, config.trading, config)
            balance_resp = client.get_balance()
            
            # 잔고 정보 파싱
            balance_data = {
                "account": account_name,
                "useYn": use_yn,
                "status": "success",
                "balance": None,
                "error": None,
            }
            
            if balance_resp.get('code') == '0' and balance_resp.get('data'):
                data = balance_resp['data'][0]
                details = data.get('details', [])
                
                # 각 통화별 잔고 정보
                currencies = []
                total_equity = float(data.get('totalEq', '0'))
                
                for detail in details:
                    ccy = detail.get('ccy', '')
                    avail_bal = float(detail.get('availBal', '0'))
                    eq = float(detail.get('eq', '0'))
                    if avail_bal > 0 or eq > 0:
                        currencies.append({
                            "currency": ccy,
                            "available": avail_bal,
                            "equity": eq,
                        })
                
                balance_data["balance"] = {
                    "total_equity": total_equity,
                    "currencies": currencies,
                }
            else:
                balance_data["status"] = "error"
                balance_data["error"] = balance_resp.get('msg', 'Unknown error')
                balance_data["raw_response"] = balance_resp
            
            account_balances.append(balance_data)
            
        except Exception as e:
            account_balances.append({
                "account": account_name,
                "useYn": use_yn,
                "status": "error",
                "balance": None,
                "error": str(e),
            })
    
    # 활성 계정 개수
    active_accounts = config.get_active_accounts()
    
    return JsonResponse({
        "ok": True,
        "config": {
            "trading_enabled": config.enable_trading,
            "default_symbol": config.trading_symbol,
            "default_leverage": config.trading_leverage,
            "default_td_mode": config.trading_td_mode,
            "default_tp_percent": config.take_profit_percent,
            "default_sl_percent": config.stop_loss_percent,
            "webhook_secret_set": bool(config.webhook_secret),
        },
        "accounts": accounts_info,
        "account_names": config.get_account_names(),
        "active_accounts": len(active_accounts),
        "active_account_names": [acc.get("name", "unknown") for acc in active_accounts],
        "balances": account_balances,
    })


@csrf_exempt
def discord_check(request: HttpRequest):
    """
    Discord 테스트 엔드포인트.
    Discord 웹훅이 정상 작동하는지 확인용.
    
    GET /webhook/discord-check/
    """
    webhook_url = get_discord_webhook_url()
    
    if not webhook_url:
        return JsonResponse({
            "ok": False,
            "error": "DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다",
            "webhook_configured": False,
        }, status=400)
    
    # 테스트 메시지 전송
    success = send_discord_message(
        webhook_url=webhook_url,
        title="🧪 Discord 테스트 메시지",
        description="TriggerHub 서버에서 Discord 연동 테스트를 실행했습니다.",
        color=0x0099FF,  # Blue
        fields=[
            {"name": "서버 상태", "value": "정상", "inline": True},
            {"name": "테스트 시간", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True},
            {"name": "메시지", "value": "이 메시지가 보이면 Discord 연동이 정상적으로 작동합니다! ✅", "inline": False},
        ],
    )
    
    if success:
        return JsonResponse({
            "ok": True,
            "message": "Discord 테스트 메시지가 성공적으로 전송되었습니다",
            "webhook_configured": True,
            "webhook_url_set": True,
        })
    else:
        return JsonResponse({
            "ok": False,
            "error": "Discord 메시지 전송 실패",
            "webhook_configured": True,
            "webhook_url_set": True,
        }, status=500)


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
    
    # 상세 로그 출력
    logger.info("\n" + "=" * 60)
    logger.info("📥 [WEBHOOK TEST] 웹훅 수신!")
    logger.info("=" * 60)
    logger.info(f"⏰ 시간: {timestamp}")
    logger.info(f"🌐 IP: {client_ip}")
    logger.info(f"📱 User-Agent: {user_agent[:50]}...")
    logger.info(f"📋 Content-Type: {content_type}")
    logger.info(f"✅ JSON 유효: {json_valid}")
    logger.info("-" * 60)
    logger.info(f"📦 Raw Body: {raw_body[:500]}")
    logger.info("-" * 60)
    logger.info(f"📊 Parsed Payload: {json.dumps(payload, indent=2, ensure_ascii=False)[:500]}")
    logger.info("=" * 60 + "\n")
    
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
