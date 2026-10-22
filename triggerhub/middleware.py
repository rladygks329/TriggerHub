"""
에러 처리 미들웨어
모든 예외를 잡아서 Discord로 알림을 보냅니다.
"""
import logging
import traceback
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from trading.discord import get_discord_webhook_url, send_discord_message

logger = logging.getLogger(__name__)


class ErrorNotificationMiddleware(MiddlewareMixin):
    """
    에러 발생 시 Discord로 알림을 보내는 미들웨어
    """
    
    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        """
        예외 발생 시 호출되는 메서드
        """
        try:
            webhook_url = get_discord_webhook_url()
            if not webhook_url:
                logger.warning("DISCORD_WEBHOOK_URL이 설정되지 않아 에러 알림을 보낼 수 없습니다.")
                return None
            
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
            
            # 클라이언트 IP
            client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
            error_details.append({
                "name": "클라이언트 IP",
                "value": client_ip[:50],
                "inline": True,
            })
            
            # 예외 정보
            exc_type = type(exception).__name__
            exc_message = str(exception)
            exc_traceback = traceback.format_exc()
            
            error_details.append({
                "name": "예외 타입",
                "value": exc_type,
                "inline": True,
            })
            error_details.append({
                "name": "예외 메시지",
                "value": exc_message[:1000],
                "inline": False,
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
            
            # 요청 본문 (있는 경우, 최대 500자)
            try:
                if hasattr(request, 'body') and request.body:
                    body_preview = request.body.decode('utf-8', errors='ignore')[:500]
                    error_details.append({
                        "name": "요청 본문 (일부)",
                        "value": f"```\n{body_preview}\n```",
                        "inline": False,
                    })
            except Exception:
                pass
            
            # Discord 메시지 전송
            color = 0xFF0000  # Red
            title = f"🚨 예외 발생: {exc_type}"
            description = f"**{exc_type}** 예외가 발생했습니다."
            
            send_discord_message(
                webhook_url=webhook_url,
                title=title,
                description=description,
                color=color,
                fields=error_details,
            )
            
            logger.error(f"Discord 에러 알림 전송 완료: {exc_type} - {exc_message[:100]}")
        except Exception as e:
            logger.error(f"Discord 에러 알림 전송 실패: {e}")
        
        # None을 반환하면 Django의 기본 에러 처리가 계속 진행됩니다
        return None

