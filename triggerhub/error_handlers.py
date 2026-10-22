"""
Django 에러 핸들러
에러 발생 시 Discord로 알림을 보냅니다.
"""
import logging
import traceback
from datetime import datetime
from typing import Optional

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from trading.discord import get_discord_webhook_url, send_discord_message

logger = logging.getLogger(__name__)


def _send_error_notification(
    request: HttpRequest,
    status_code: int,
    error_message: str,
    exception: Optional[Exception] = None,
    error_type: str = "Error",
) -> None:
    """
    에러 발생 시 Discord로 알림 전송
    
    Args:
        request: HTTP 요청 객체
        status_code: HTTP 상태 코드
        error_message: 에러 메시지
        exception: 예외 객체 (있는 경우)
        error_type: 에러 타입 (500, 404, 400 등)
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL이 설정되지 않아 에러 알림을 보낼 수 없습니다.")
        return
    
    try:
        # 에러 상세 정보 수집
        error_details = []
        
        # 요청 정보
        error_details.append({
            "name": "요청 경로",
            "value": request.path[:200],
            "inline": False,
        })
        error_details.append({
            "name": "요청 메서드",
            "value": request.method,
            "inline": True,
        })
        error_details.append({
            "name": "상태 코드",
            "value": str(status_code),
            "inline": True,
        })
        
        # 클라이언트 IP
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
        error_details.append({
            "name": "클라이언트 IP",
            "value": client_ip[:50],
            "inline": True,
        })
        
        # 에러 메시지
        error_details.append({
            "name": "에러 메시지",
            "value": error_message[:1000],
            "inline": False,
        })
        
        # 예외 상세 정보 (있는 경우)
        if exception:
            exc_type = type(exception).__name__
            exc_traceback = traceback.format_exc()
            error_details.append({
                "name": "예외 타입",
                "value": exc_type,
                "inline": True,
            })
            error_details.append({
                "name": "스택 트레이스",
                "value": f"```\n{exc_traceback[:1500]}\n```",
                "inline": False,
            })
        
        # 요청 헤더 (일부만)
        user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')[:100]
        error_details.append({
            "name": "User-Agent",
            "value": user_agent,
            "inline": False,
        })
        
        # Discord 메시지 전송
        color = 0xFF0000  # Red
        title = f"🚨 서버 에러 발생 ({error_type})"
        description = f"**{error_type}** 에러가 발생했습니다."
        
        send_discord_message(
            webhook_url=webhook_url,
            title=title,
            description=description,
            color=color,
            fields=error_details,
        )
        
        logger.info(f"Discord 에러 알림 전송 완료: {error_type} - {error_message[:100]}")
    except Exception as e:
        logger.error(f"Discord 에러 알림 전송 실패: {e}")


@csrf_exempt
def handler500(request: HttpRequest, exception: Optional[Exception] = None) -> HttpResponse:
    """
    500 Internal Server Error 핸들러
    """
    error_message = "서버 내부 오류가 발생했습니다."
    
    if exception:
        error_message = str(exception)
        logger.error(f"500 에러 발생: {error_message}\n{traceback.format_exc()}")
    else:
        logger.error("500 에러 발생 (예외 정보 없음)")
    
    # Discord 알림 전송
    _send_error_notification(
        request=request,
        status_code=500,
        error_message=error_message,
        exception=exception,
        error_type="500 Internal Server Error",
    )
    
    # JSON 응답 반환
    return JsonResponse({
        "ok": False,
        "error": "internal_server_error",
        "message": "서버 내부 오류가 발생했습니다.",
    }, status=500)


@csrf_exempt
def handler404(request: HttpRequest, exception: Optional[Exception] = None) -> HttpResponse:
    """
    404 Not Found 핸들러
    """
    error_message = f"요청한 경로를 찾을 수 없습니다: {request.path}"
    logger.warning(f"404 에러 발생: {request.path}")
    
    # Discord 알림 전송 (선택적 - 404는 너무 많을 수 있으므로 주석 처리 가능)
    # _send_error_notification(
    #     request=request,
    #     status_code=404,
    #     error_message=error_message,
    #     exception=exception,
    #     error_type="404 Not Found",
    # )
    
    return JsonResponse({
        "ok": False,
        "error": "not_found",
        "message": f"요청한 경로를 찾을 수 없습니다: {request.path}",
    }, status=404)


@csrf_exempt
def handler400(request: HttpRequest, exception: Optional[Exception] = None) -> HttpResponse:
    """
    400 Bad Request 핸들러
    """
    error_message = "잘못된 요청입니다."
    
    if exception:
        error_message = str(exception)
        logger.warning(f"400 에러 발생: {error_message}")
    else:
        logger.warning("400 에러 발생 (예외 정보 없음)")
    
    # Discord 알림 전송
    _send_error_notification(
        request=request,
        status_code=400,
        error_message=error_message,
        exception=exception,
        error_type="400 Bad Request",
    )
    
    return JsonResponse({
        "ok": False,
        "error": "bad_request",
        "message": error_message,
    }, status=400)


@csrf_exempt
def handler403(request: HttpRequest, exception: Optional[Exception] = None) -> HttpResponse:
    """
    403 Forbidden 핸들러
    """
    error_message = "접근이 거부되었습니다."
    
    if exception:
        error_message = str(exception)
        logger.warning(f"403 에러 발생: {error_message}")
    else:
        logger.warning("403 에러 발생 (예외 정보 없음)")
    
    # Discord 알림 전송
    _send_error_notification(
        request=request,
        status_code=403,
        error_message=error_message,
        exception=exception,
        error_type="403 Forbidden",
    )
    
    # 상세한 에러 정보를 포함한 응답
    error_data = {
        "ok": False,
        "error": "forbidden",
        "message": error_message,
    }
    
    # PermissionDenied 예외에서 추가 정보 추출
    if exception and hasattr(exception, 'args') and exception.args:
        error_msg = str(exception.args[0])
        # 시크릿 불일치인 경우 더 구체적인 에러 코드 제공
        if "시크릿" in error_msg or "secret" in error_msg.lower():
            error_data["error"] = "invalid_secret"
        elif "enable_trading" in error_msg or "거래 비활성화" in error_msg:
            error_data["error"] = "trading_disabled"
        error_data["message"] = error_msg
    
    return JsonResponse(error_data, status=403)

