import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


class OkxClient:
    """
    최소한의 OKX REST API 클라이언트 (현물/선물 주문용 뼈대).
    실제 주문 전에는 반드시 모의/소액으로 테스트 하세요.
    """

    def __init__(self, api_key: str, secret_key: str, passphrase: str, *, is_demo: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = "https://www.okx.com" if not is_demo else "https://www.okx.com"

    def _timestamp(self) -> str:
        # OKX는 ISO 8601 (UTC) 형식의 타임스탬프를 요구함. milliseconds까지 포함.
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(
            self.secret_key.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        ts = self._timestamp()
        sign = self._sign(ts, method, path, body)
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body_str = "" if json_body is None else __import__("json").dumps(json_body, separators=(",", ":"))
        headers = self._headers(method, path, body_str)
        url = self.base_url + path
        resp = requests.request(method, url, headers=headers, data=body_str or None, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def place_market_order(
        self,
        inst_id: str,
        side: str,
        sz: str,
        td_mode: str = "cross",
    ) -> Dict[str, Any]:
        """
        OKX 시장가 주문 예시 (선물 기준, 필요에 따라 instId/tdMode 등 조정).
        """
        path = "/api/v5/trade/order"
        body = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,  # buy / sell
            "ordType": "market",
            "sz": sz,
        }
        return self._request("POST", path, body)


