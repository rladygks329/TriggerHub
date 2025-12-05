import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .config import Config


class OkxClient:
    """
    OKX REST API 클라이언트.
    실제 검증된 코드 기반으로 구현됨.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        *,
        is_demo: bool = False,
        leverage: int = 10,
        td_mode: str = "cross",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = "https://www.okx.com"
        self.is_demo = is_demo
        self.leverage = leverage
        self.td_mode = td_mode  # cross 또는 isolated

    # ============================================
    # API 인증
    # ============================================
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """OKX API 서명 생성"""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    def _get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
        """API 요청 헤더 생성"""
        timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        signature = self._generate_signature(timestamp, method, request_path, body)
        
        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        # 데모 모드일 경우 시뮬레이션 헤더 추가
        if self.is_demo:
            headers["x-simulated-trading"] = "1"
        
        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """API 요청 실행"""
        body_str = ""
        if body:
            body_str = json.dumps(body) if isinstance(body, dict) else body
        
        headers = self._get_headers(method, path, body_str)
        url = self.base_url + path
        
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
        
        resp.raise_for_status()
        return resp.json()

    # ============================================
    # 시세 조회
    # ============================================
    def get_ticker(self, inst_id: str) -> Dict[str, Any]:
        """현재 시세 조회"""
        path = f'/api/v5/market/ticker?instId={inst_id}'
        return self._request("GET", path)

    def get_last_price(self, inst_id: str) -> Decimal:
        """특정 상품의 현재 가격(마지막 체결가) 반환"""
        resp = self.get_ticker(inst_id)
        data = resp.get("data") or []
        if not data:
            raise ValueError(f"가격 조회 실패: {inst_id}")
        return Decimal(data[0]["last"])

    def get_price_info(self, inst_id: str) -> Dict[str, Any]:
        """상세 가격 정보 조회"""
        resp = self.get_ticker(inst_id)
        if resp.get('code') == '0' and resp.get('data'):
            data = resp['data'][0]
            return {
                "last": float(data['last']),
                "bid": float(data['bidPx']),
                "ask": float(data['askPx']),
                "vol_24h": float(data.get('vol24h', 0)),
            }
        raise ValueError(f"가격 조회 실패: {inst_id}")

    # ============================================
    # 잔고 조회
    # ============================================
    def get_balance(self) -> Dict[str, Any]:
        """계좌 잔고 조회"""
        path = '/api/v5/account/balance'
        return self._request("GET", path)

    def get_usdt_balance(self) -> float:
        """USDT 사용 가능 잔고 반환"""
        resp = self.get_balance()
        if resp.get('code') == '0' and resp.get('data'):
            details = resp['data'][0]['details']
            for detail in details:
                if detail['ccy'] == 'USDT':
                    return float(detail['availBal'])
        return 0.0

    def calculate_order_size(
        self,
        inst_id: str,
        leverage: int,
        balance_percent: float = 100.0,
    ) -> str:
        """
        잔고 기반으로 주문 수량 계산.
        
        Args:
            inst_id: 거래 상품 (예: ETH-USDT-SWAP)
            leverage: 레버리지 배수
            balance_percent: 사용할 잔고 비율 (기본값: 100%)
        
        Returns:
            계약 수량 (문자열)
        
        계산 공식:
            주문 가능 금액 = USDT 잔고 × (balance_percent / 100)
            레버리지 적용 금액 = 주문 가능 금액 × 레버리지
            계약 수량 = 레버리지 적용 금액 / 현재가 / 계약 크기
        """
        # 1. USDT 잔고 조회
        usdt_balance = self.get_usdt_balance()
        if usdt_balance <= 0:
            raise ValueError("USDT 잔고가 없습니다")
        
        # 2. 사용할 금액 계산 (퍼센트 적용)
        available_margin = usdt_balance * (balance_percent / 100.0)
        
        # 3. 현재가 조회
        current_price = float(self.get_last_price(inst_id))
        
        # 4. 계약 크기 결정 (SWAP 상품별 기본 계약 크기)
        # ETH: 0.1 ETH = 1계약, BTC: 0.01 BTC = 1계약
        if "ETH" in inst_id:
            contract_value = 0.1  # ETH는 0.1 ETH = 1계약
        elif "BTC" in inst_id:
            contract_value = 0.01  # BTC는 0.01 BTC = 1계약
        else:
            contract_value = 0.1  # 기본값
        
        # 5. 계약당 USDT 가치
        contract_usdt_value = current_price * contract_value
        
        # 6. 레버리지 적용하여 주문 가능 계약 수 계산
        # 필요 증거금 = 계약 가치 / 레버리지
        # 주문 가능 계약 수 = 사용 가능 증거금 / (계약당 USDT 가치 / 레버리지)
        max_contracts = (available_margin * leverage) / contract_usdt_value
        
        # 7. 소수점 내림 (0.001 단위)
        contracts = int(max_contracts * 1000) / 1000  # 0.001 단위로 내림
        
        if contracts < 0.001:
            raise ValueError(
                f"잔고 부족: USDT {usdt_balance:.2f}, "
                f"최소 주문 수량(0.001 계약)을 위해 필요한 증거금: "
                f"${contract_usdt_value / leverage * 0.001:.4f}"
            )
        
        print(f"[OKX] 수량 계산: 잔고=${usdt_balance:.2f}, 현재가=${current_price:.2f}, "
              f"레버리지={leverage}x, 계약수={contracts:.3f}")
        
        return str(contracts)

    # ============================================
    # 레버리지 설정
    # ============================================
    def set_leverage(self, inst_id: str, leverage: Optional[int] = None, margin_mode: Optional[str] = None) -> Dict[str, Any]:
        """레버리지 설정"""
        path = '/api/v5/account/set-leverage'
        
        body = {
            "instId": inst_id,
            "lever": str(leverage or self.leverage),
            "mgnMode": margin_mode or self.td_mode
        }
        
        return self._request("POST", path, body)

    # ============================================
    # 포지션 조회
    # ============================================
    def get_positions(self, inst_type: str = "SWAP") -> Dict[str, Any]:
        """포지션 조회"""
        path = f'/api/v5/account/positions?instType={inst_type}'
        return self._request("GET", path)

    def get_active_positions(self, inst_type: str = "SWAP") -> List[Dict[str, Any]]:
        """활성 포지션만 반환"""
        resp = self.get_positions(inst_type)
        if resp.get('code') == '0':
            positions = resp.get('data', [])
            return [pos for pos in positions if float(pos.get('pos', 0)) != 0]
        return []

    # ============================================
    # 상품 조회
    # ============================================
    def get_instruments(self, inst_type: str = "SWAP", uly: Optional[str] = None) -> Dict[str, Any]:
        """거래 상품 조회"""
        path = f'/api/v5/public/instruments?instType={inst_type}'
        if uly:
            path += f'&uly={uly}'
        return self._request("GET", path)

    # ============================================
    # 시장가 주문
    # ============================================
    def place_market_order(
        self,
        inst_id: str,
        side: str,
        sz: str,
        td_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """시장가 주문"""
        path = '/api/v5/trade/order'
        
        body = {
            "instId": inst_id,
            "tdMode": td_mode or self.td_mode,
            "side": side,  # buy / sell
            "ordType": "market",
            "sz": sz,
        }
        
        return self._request("POST", path, body)

    def place_market_order_with_tp_sl(
        self,
        inst_id: str,
        side: str,
        sz: str,
        tp_percent: Optional[float] = None,
        sl_percent: Optional[float] = None,
        td_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        TP(Take Profit)와 SL(Stop Loss)을 포함한 시장가 주문.

        Args:
            inst_id: 거래 상품 (예: BTC-USDT-SWAP)
            side: "buy" 또는 "sell"
            sz: 주문 수량
            tp_percent: 익절 퍼센트 (예: 2.3 = 2.3%)
            sl_percent: 손절 퍼센트 (예: 0.7 = 0.7%)
            td_mode: 마진 모드 (cross/isolated)

        Returns:
            OKX API 응답
        """
        path = "/api/v5/trade/order"

        body: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode or self.td_mode,
            "side": side,
            "ordType": "market",
            "sz": sz,
        }

        # TP/SL이 설정된 경우 현재 가격 기반으로 계산
        if tp_percent is not None or sl_percent is not None:
            current_price = self.get_last_price(inst_id)

            attach_algo: Dict[str, str] = {}

            if tp_percent is not None:
                # 매수: 가격 상승이 이익 / 매도: 가격 하락이 이익
                if side == "buy":
                    tp_price = current_price * (1 + Decimal(str(tp_percent)) / 100)
                else:
                    tp_price = current_price * (1 - Decimal(str(tp_percent)) / 100)

                # 소수점 적절히 처리 (가격에 따라 조정 필요할 수 있음)
                attach_algo["tpTriggerPx"] = str(tp_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
                attach_algo["tpOrdPx"] = "-1"  # 시장가로 체결
                attach_algo["tpTriggerPxType"] = "last"  # 마지막 체결가 기준

            if sl_percent is not None:
                # 매수: 가격 하락이 손실 / 매도: 가격 상승이 손실
                if side == "buy":
                    sl_price = current_price * (1 - Decimal(str(sl_percent)) / 100)
                else:
                    sl_price = current_price * (1 + Decimal(str(sl_percent)) / 100)

                attach_algo["slTriggerPx"] = str(sl_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
                attach_algo["slOrdPx"] = "-1"  # 시장가로 체결
                attach_algo["slTriggerPxType"] = "last"  # 마지막 체결가 기준

            if attach_algo:
                body["attachAlgoOrds"] = [attach_algo]

        return self._request("POST", path, body)

    # ============================================
    # 주문 관련 유틸리티
    # ============================================
    def place_order_with_leverage(
        self,
        inst_id: str,
        side: str,
        sz: str,
        leverage: Optional[int] = None,
        tp_percent: Optional[float] = None,
        sl_percent: Optional[float] = None,
        td_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        레버리지 설정 후 TP/SL 포함 주문.
        자동매매에서 주로 사용하는 통합 메서드.
        """
        # 1. 레버리지 설정
        margin_mode = td_mode or self.td_mode
        lev = leverage or self.leverage
        
        try:
            self.set_leverage(inst_id, lev, margin_mode)
        except Exception as e:
            # 레버리지 설정 실패해도 주문은 진행 (이미 설정되어 있을 수 있음)
            print(f"[OKX] 레버리지 설정 경고: {e}")

        # 2. 주문 실행
        if tp_percent is not None or sl_percent is not None:
            return self.place_market_order_with_tp_sl(
                inst_id=inst_id,
                side=side,
                sz=sz,
                tp_percent=tp_percent,
                sl_percent=sl_percent,
                td_mode=margin_mode,
            )
        else:
            return self.place_market_order(
                inst_id=inst_id,
                side=side,
                sz=sz,
                td_mode=margin_mode,
            )

    # ============================================
    # 결과 확인 유틸리티
    # ============================================
    @staticmethod
    def is_success(resp: Dict[str, Any]) -> bool:
        """API 응답이 성공인지 확인"""
        return resp.get('code') == '0'

    @staticmethod
    def get_order_id(resp: Dict[str, Any]) -> Optional[str]:
        """응답에서 주문 ID 추출"""
        if resp.get('code') == '0' and resp.get('data'):
            return resp['data'][0].get('ordId')
        return None

    @staticmethod
    def get_error_message(resp: Dict[str, Any]) -> str:
        """응답에서 에러 메시지 추출"""
        msg = resp.get('msg', 'Unknown error')
        # 상세 에러 추가
        if resp.get('data'):
            for item in resp['data']:
                if item.get('sMsg'):
                    msg += f" | {item.get('sCode')}: {item.get('sMsg')}"
        return msg

    @classmethod
    def from_config(cls, config: Optional['Config'] = None) -> 'OkxClient':
        """
        config.json 설정에서 OkxClient 인스턴스 생성.
        
        Args:
            config: Config 인스턴스. None이면 자동으로 로드.
        
        Returns:
            OkxClient 인스턴스
        """
        if config is None:
            from .config import get_config
            config = get_config()
        
        return cls(
            api_key=config.api_key,
            secret_key=config.secret_key,
            passphrase=config.passphrase,
            is_demo=config.is_demo,
            leverage=config.trading_leverage,
            td_mode=config.trading_td_mode,
        )
