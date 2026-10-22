import os
import json
import logging
from typing import Optional, Dict, Any
import requests

# 로거 설정
logger = logging.getLogger(__name__)


def send_discord_message(
    webhook_url: str,
    content: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    color: int = 0x00FF00,  # Green
    fields: Optional[list] = None,
) -> bool:
    """
    Discord 웹훅으로 메시지 전송
    
    Args:
        webhook_url: Discord 웹훅 URL
        content: 일반 텍스트 메시지
        title: 임베드 제목
        description: 임베드 설명
        color: 임베드 색상 (16진수)
        fields: 임베드 필드 리스트 [{"name": "...", "value": "...", "inline": True/False}]
    
    Returns:
        성공 여부
    """
    try:
        embed = None
        if title or description or fields:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "fields": fields or [],
                "timestamp": None,
            }
            # None 값 제거
            embed = {k: v for k, v in embed.items() if v is not None}
        
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        
        if not payload:
            return False
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[DISCORD ERROR] {e}")
        return False


def send_trade_notification(
    webhook_url: str,
    symbol: str,
    side: str,
    size: str,
    order_id: Optional[str] = None,
    status: str = "success",
    error: Optional[str] = None,
) -> bool:
    """
    거래 알림을 Discord로 전송
    
    Args:
        webhook_url: Discord 웹훅 URL
        symbol: 거래 심볼
        side: buy/sell
        size: 주문 수량
        order_id: 주문 ID
        status: success/error
        error: 에러 메시지 (에러인 경우)
    """
    if status == "success":
        color = 0x00FF00  # Green
        title = f"✅ 주문 성공: {side.upper()}"
        description = f"**{symbol}** {side.upper()} 주문이 성공적으로 체결되었습니다."
        fields = [
            {"name": "심볼", "value": symbol, "inline": True},
            {"name": "방향", "value": side.upper(), "inline": True},
            {"name": "수량", "value": size, "inline": True},
        ]
        if order_id:
            fields.append({"name": "주문 ID", "value": order_id, "inline": False})
    else:
        color = 0xFF0000  # Red
        title = f"❌ 주문 실패: {side.upper()}"
        description = f"**{symbol}** {side.upper()} 주문이 실패했습니다."
        fields = [
            {"name": "심볼", "value": symbol, "inline": True},
            {"name": "방향", "value": side.upper(), "inline": True},
            {"name": "수량", "value": size, "inline": True},
        ]
        if error:
            fields.append({"name": "에러", "value": error[:1000], "inline": False})
    
    return send_discord_message(
        webhook_url=webhook_url,
        title=title,
        description=description,
        color=color,
        fields=fields,
    )


def get_discord_webhook_url() -> Optional[str]:
    """환경변수에서 Discord 웹훅 URL 가져오기"""
    return os.getenv("DISCORD_WEBHOOK_URL")

