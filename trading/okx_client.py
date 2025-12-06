import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import requests

# 로거 설정
logger = logging.getLogger(__name__)

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
        base_url: str = "https://www.okx.com",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = base_url
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
        response_json = resp.json()
        
        # 주문 응답 로깅
        if "/trade/order" in path:
            logger.info(f"[OKX] 주문 응답: {json.dumps(response_json, indent=2)}")
            print(f"[OKX] 주문 응답: {json.dumps(response_json, indent=2)}", flush=True)
        
        return response_json

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

    def get_instrument_info(self, inst_id: str) -> Dict[str, Any]:
        """Instrument 정보 조회 (lot size 등)"""
        path = f'/api/v5/public/instruments?instType=SWAP&instId={inst_id}'
        resp = self._request("GET", path)
        if resp.get('code') == '0' and resp.get('data') and len(resp['data']) > 0:
            inst_info = resp['data'][0]
            # 디버깅: 실제 OKX에서 받은 lot size 값 로깅
            print(f"[OKX] Instrument 정보 조회: instId={inst_id}, lotSz={inst_info.get('lotSz')}, minSz={inst_info.get('minSz')}, ctVal={inst_info.get('ctVal')}", flush=True)
            return inst_info
        raise ValueError(f"Instrument 정보 조회 실패: {inst_id}")

    def round_to_lot_size(self, quantity: str, inst_id: str) -> str:
        """
        주문 수량을 lot size의 배수로 반올림 (내림).
        
        Args:
            quantity: 주문 수량 (문자열)
            inst_id: 거래 상품 (예: ETH-USDT-SWAP)
        
        Returns:
            lot size의 배수로 반올림된 수량 (문자열)
        
        예시:
            - lot size = 0.1, quantity = 0.401 → 0.4 (4 * 0.1)
            - lot size = 0.1, quantity = 0.1 → 0.1 (1 * 0.1)
            - lot size = 0.001, quantity = 0.123 → 0.123 (123 * 0.001)
        """
        logger.info(f"[OKX] round_to_lot_size 호출: quantity={quantity}, inst_id={inst_id}")
        print(f"[OKX] round_to_lot_size 호출: quantity={quantity}, inst_id={inst_id}", flush=True)
        try:
            # Instrument 정보에서 lot size 가져오기
            logger.info(f"[OKX] Instrument 정보 조회 시작: {inst_id}")
            print(f"[OKX] Instrument 정보 조회 시작: {inst_id}", flush=True)
            inst_info = self.get_instrument_info(inst_id)
            lot_sz = Decimal(str(inst_info.get('lotSz', '0.001')))  # 기본값 0.001
            min_sz = Decimal(str(inst_info.get('minSz', '0.001')))  # 최소 주문 수량
            
            # 수량을 Decimal로 변환
            qty = Decimal(str(quantity))
            
            # 디버깅 로그
            logger.info(f"[OKX] Lot size 반올림: 원본={qty}, lot_sz={lot_sz}, min_sz={min_sz}")
            print(f"[OKX] Lot size 반올림: 원본={qty}, lot_sz={lot_sz}, min_sz={min_sz}", flush=True)
            
            # lot size의 배수로 내림 (예: 0.401 / 0.1 = 4.01 → 4 → 4 * 0.1 = 0.4)
            if lot_sz > 0:
                multiplier = (qty / lot_sz).quantize(Decimal('1'), rounding=ROUND_DOWN)
                rounded = multiplier * lot_sz
            else:
                rounded = qty
            
            # 최소 주문 수량 확인
            # 주의: minSz는 최소 주문 수량이지만, lot size의 배수여야 함
            # 예: lotSz=0.001, minSz=0.1이면, 최소 주문은 0.1 (100 * 0.001)
            if rounded < min_sz:
                # minSz를 lot size의 배수로 올림
                if lot_sz > 0:
                    min_multiplier = (min_sz / lot_sz).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    if (min_sz / lot_sz) % 1 != 0:
                        min_multiplier += 1  # 올림
                    rounded = min_multiplier * lot_sz
                    print(f"[OKX] ⚠️ 반올림된 수량({rounded})이 최소 수량({min_sz})보다 작음, lot size 배수로 조정: {rounded}", flush=True)
                else:
                    rounded = min_sz
                    print(f"[OKX] ⚠️ 반올림된 수량({rounded})이 최소 수량({min_sz})보다 작음, 최소 수량 사용", flush=True)
            
            logger.info(f"[OKX] ✅ Lot size 반올림 결과: {qty} → {rounded} (lot_sz={lot_sz}, min_sz={min_sz}, 배수={multiplier if lot_sz > 0 else 'N/A'})")
            print(f"[OKX] ✅ Lot size 반올림 결과: {qty} → {rounded} (lot_sz={lot_sz}, min_sz={min_sz}, 배수={multiplier if lot_sz > 0 else 'N/A'})", flush=True)
            return str(rounded)
        except Exception as e:
            # 실패 시 기본값 0.001로 반올림
            import traceback
            print(f"[OKX] ❌ Lot size 반올림 실패, 기본값 사용: {e}", flush=True)
            print(f"[OKX] 예외 상세: {traceback.format_exc()}", flush=True)
            qty = Decimal(str(quantity))
            lot_sz = Decimal('0.001')
            multiplier = (qty / lot_sz).quantize(Decimal('1'), rounding=ROUND_DOWN)
            rounded = multiplier * lot_sz
            if rounded < Decimal('0.001'):
                rounded = Decimal('0.001')
            print(f"[OKX] 기본값 사용 결과: {qty} → {rounded}", flush=True)
            return str(rounded)

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
        # 안전 마진: 95%만 사용 (기존 포지션, 미체결 주문, 수수료 등 고려)
        safety_margin = 0.97
        max_contracts = (available_margin * leverage * safety_margin) / contract_usdt_value
        
        logger.info(f"[OKX] 수량 계산 상세: available_margin={available_margin:.2f}, leverage={leverage}, safety_margin={safety_margin}, contract_usdt_value={contract_usdt_value:.2f}")
        print(f"[OKX] 수량 계산 상세: available_margin={available_margin:.2f}, leverage={leverage}, safety_margin={safety_margin}, contract_usdt_value={contract_usdt_value:.2f}", flush=True)
        
        # 7. lot size에 맞게 반올림
        contracts_str = str(max_contracts)
        logger.info(f"[OKX] 수량 계산: 잔고=${usdt_balance:.2f}, 현재가=${current_price:.2f}, 레버리지={leverage}x, 계산된 계약수={max_contracts:.6f} (반올림 전)")
        print(f"[OKX] 수량 계산: 잔고=${usdt_balance:.2f}, 현재가=${current_price:.2f}, "
              f"레버리지={leverage}x, 계산된 계약수={max_contracts:.6f} (반올림 전)", flush=True)
        
        try:
            contracts_rounded = self.round_to_lot_size(contracts_str, inst_id)
            contracts = float(contracts_rounded)
            
            # 최소 수량은 lot size 반올림 후 확인 (round_to_lot_size에서 이미 처리됨)
            if contracts <= 0:
                raise ValueError(
                    f"잔고 부족: USDT {usdt_balance:.2f}, "
                    f"계산된 계약 수량이 0 이하입니다."
                )
            
            logger.info(f"[OKX] 수량 계산 완료: 최종 계약수={contracts:.6f} (lot size 반올림 후)")
            print(f"[OKX] 수량 계산 완료: 최종 계약수={contracts:.6f} (lot size 반올림 후)", flush=True)
            
            return contracts_rounded
        except Exception as e:
            import traceback
            logger.error(f"[OKX] ❌ 수량 계산 중 오류: {e}\n{traceback.format_exc()}")
            print(f"[OKX] ❌ 수량 계산 중 오류: {e}", flush=True)
            print(f"[OKX] 예외 상세: {traceback.format_exc()}", flush=True)
            raise

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
        
        logger.info(f"[OKX] 주문 요청 body: {body}")
        print(f"[OKX] 주문 요청 body: {json.dumps(body, indent=2)}", flush=True)

        # TP/SL이 설정된 경우 현재 가격 기반으로 계산
        if tp_percent is not None or sl_percent is not None:
            current_price = self.get_last_price(inst_id)
            print(f"[OKX] TP/SL 계산 시작: 현재가={current_price}, tp_percent={tp_percent}, sl_percent={sl_percent}, side={side}", flush=True)

            attach_algo: Dict[str, str] = {}

            if tp_percent is not None:
                # 매수: 가격 상승이 이익 / 매도: 가격 하락이 이익
                if side == "buy":
                    tp_price = current_price * (1 + Decimal(str(tp_percent)) / 100)
                else:
                    tp_price = current_price * (1 - Decimal(str(tp_percent)) / 100)

                # 소수점 적절히 처리 (가격에 따라 조정 필요할 수 있음)
                tp_trigger_px = str(tp_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
                attach_algo["tpTriggerPx"] = tp_trigger_px
                attach_algo["tpOrdPx"] = "-1"  # 시장가로 체결
                attach_algo["tpTriggerPxType"] = "last"  # 마지막 체결가 기준
                print(f"[OKX] ✅ TP 설정: {current_price} → {tp_trigger_px} (+{tp_percent}%)", flush=True)

            if sl_percent is not None:
                # 매수: 가격 하락이 손실 / 매도: 가격 상승이 손실
                if side == "buy":
                    sl_price = current_price * (1 - Decimal(str(sl_percent)) / 100)
                else:
                    sl_price = current_price * (1 + Decimal(str(sl_percent)) / 100)

                sl_trigger_px = str(sl_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
                attach_algo["slTriggerPx"] = sl_trigger_px
                attach_algo["slOrdPx"] = "-1"  # 시장가로 체결
                attach_algo["slTriggerPxType"] = "last"  # 마지막 체결가 기준
                print(f"[OKX] ✅ SL 설정: {current_price} → {sl_trigger_px} (-{sl_percent}%)", flush=True)

            if attach_algo:
                body["attachAlgoOrds"] = [attach_algo]
                print(f"[OKX] TP/SL 주문 첨부: {attach_algo}", flush=True)
            else:
                print(f"[OKX] ⚠️ TP/SL 주문이 첨부되지 않음", flush=True)

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
        print(f"[OKX] place_order_with_leverage 호출: inst_id={inst_id}, side={side}, sz={sz}, leverage={leverage}, tp={tp_percent}, sl={sl_percent}", flush=True)
        
        # 1. 레버리지 설정
        margin_mode = td_mode or self.td_mode
        lev = leverage or self.leverage
        
        try:
            self.set_leverage(inst_id, lev, margin_mode)
        except Exception as e:
            # 레버리지 설정 실패해도 주문은 진행 (이미 설정되어 있을 수 있음)
            print(f"[OKX] 레버리지 설정 경고: {e}")

        # 2. 주문 수량을 lot size에 맞게 반올림
        logger.info(f"[OKX] 주문 수량 반올림 시작: 원본={sz}, inst_id={inst_id}")
        print(f"[OKX] 주문 수량 반올림 시작: 원본={sz}, inst_id={inst_id}", flush=True)
        try:
            sz_rounded = self.round_to_lot_size(sz, inst_id)
            logger.info(f"[OKX] 주문 수량 반올림 완료: {sz} → {sz_rounded}")
            print(f"[OKX] 주문 수량 반올림 완료: {sz} → {sz_rounded}", flush=True)
        except Exception as e:
            import traceback
            logger.error(f"[OKX] ⚠️ 주문 수량 반올림 실패: {e}, 원본 수량 사용\n{traceback.format_exc()}")
            print(f"[OKX] ⚠️ 주문 수량 반올림 실패: {e}, 원본 수량 사용", flush=True)
            print(f"[OKX] 예외 상세: {traceback.format_exc()}", flush=True)
            sz_rounded = sz  # 실패 시 원본 사용
        
        # 3. 주문 실행
        if tp_percent is not None or sl_percent is not None:
            return self.place_market_order_with_tp_sl(
                inst_id=inst_id,
                side=side,
                sz=sz_rounded,
                tp_percent=tp_percent,
                sl_percent=sl_percent,
                td_mode=margin_mode,
            )
        else:
            return self.place_market_order(
                inst_id=inst_id,
                side=side,
                sz=sz_rounded,
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
    
    @classmethod
    def from_account_config(cls, account_config: Dict[str, Any], trading_config: Dict[str, Any]) -> 'OkxClient':
        """
        계정 설정 딕셔너리에서 OkxClient 인스턴스 생성.
        
        Args:
            account_config: 계정 정보 딕셔너리 (api_key, secret_key, passphrase, leverage, td_mode, base_url 등)
            trading_config: 트레이딩 설정 딕셔너리 (기본 leverage, td_mode 등)
        
        Returns:
            OkxClient 인스턴스
        """
        return cls(
            api_key=account_config.get("api_key", ""),
            secret_key=account_config.get("secret_key", ""),
            passphrase=account_config.get("passphrase", ""),
            is_demo=False,  # useYn으로 관리하므로 항상 False
            leverage=account_config.get("leverage", trading_config.get("leverage", 10)),
            td_mode=account_config.get("td_mode", trading_config.get("td_mode", "cross")),
            base_url=account_config.get("base_url", "https://www.okx.com"),
        )