import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import urlencode, quote

import requests

# 로거 설정
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .config import BinanceConfig


class BinanceClient:
    """
    바이낸스 선물(Futures) REST API 클라이언트.
    OKX와 유사한 인터페이스로 구현됨.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        is_testnet: bool = False,
        leverage: int = 10,
        base_url: str = "https://fapi.binance.com",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.is_testnet = is_testnet
        self.leverage = leverage
        
        # Testnet 모드일 경우 URL 변경
        if is_testnet:
            self.base_url = "https://testnet.binancefuture.com"
        
        # 서버 시간 동기화를 위한 오프셋 (밀리초)
        # 서버 시간 = 로컬 시간 + time_offset
        self._time_offset: Optional[int] = None
        self._sync_server_time()

    # ============================================
    # 서버 시간 동기화
    # ============================================
    def _sync_server_time(self) -> None:
        """
        바이낸스 서버 시간을 조회하여 로컬 시간과의 차이를 계산합니다.
        타임스탬프 오류를 방지하기 위해 초기화 시 자동으로 호출됩니다.
        """
        try:
            # 바이낸스 서버 시간 조회 (서명 불필요)
            path = '/fapi/v1/time'
            url = self.base_url + path
            
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            server_time_data = resp.json()
            server_time = server_time_data.get('serverTime', 0)
            
            # 로컬 시간 (밀리초)
            local_time = int(time.time() * 1000)
            
            # 시간 차이 계산 (서버 시간 - 로컬 시간)
            self._time_offset = server_time - local_time
            
            logger.info(f"[BINANCE] 서버 시간 동기화 완료: 서버={server_time}, 로컬={local_time}, 오프셋={self._time_offset}ms")
            
            # 오프셋이 너무 크면 경고
            if abs(self._time_offset) > 5000:  # 5초 이상 차이
                logger.warning(f"[BINANCE] ⚠️ 서버와 로컬 시간 차이가 큽니다: {self._time_offset}ms")
        except Exception as e:
            logger.warning(f"[BINANCE] 서버 시간 동기화 실패, 로컬 시간 사용: {e}")
            self._time_offset = 0
    
    def _get_timestamp(self) -> int:
        """
        바이낸스 서버 시간에 맞춘 타임스탬프를 반환합니다.
        
        Returns:
            밀리초 단위 타임스탬프
        """
        local_time = int(time.time() * 1000)
        
        # 서버 시간 동기화가 되어 있으면 오프셋 적용
        if self._time_offset is not None:
            server_time = local_time + self._time_offset
            return server_time
        
        # 동기화 실패 시 로컬 시간 사용
        return local_time
    
    # ============================================
    # API 인증
    # ============================================
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        바이낸스 API 서명 생성
        
        바이낸스 공식 문서에 따르면:
        1. signature를 제외한 모든 파라미터를 urlencode로 쿼리 스트링 생성
        2. 이 쿼리 스트링을 HMAC-SHA256으로 서명 생성
        
        참고: urlencode는 자동으로 알파벳 순으로 정렬하고 URL 인코딩을 처리합니다.
        """
        # signature를 제외한 파라미터로 서명 생성
        params_for_sign = {k: v for k, v in params.items() if k != 'signature'}
        
        # urlencode를 사용하여 쿼리 스트링 생성 (자동 정렬 및 URL 인코딩)
        query_string = urlencode(params_for_sign, doseq=True)
        
        # HMAC-SHA256 서명 생성
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """API 요청 실행"""
        if params is None:
            params = {}
        
        headers = self._get_headers()
        url = self.base_url + path
        
        # 서명이 필요한 경우
        if signed:
            # 서버 시간에 맞춘 타임스탬프 사용
            params['timestamp'] = self._get_timestamp()
            
            # recvWindow 추가 (서버가 요청을 처리할 수 있는 시간 범위, 기본 5000ms)
            # 시간 차이가 있을 경우를 대비해 10000ms로 설정
            if 'recvWindow' not in params:
                params['recvWindow'] = 10000  # 10초
            
            # signature를 제외한 상태로 서명 생성 후 추가
            signature = self._generate_signature(params)
            params['signature'] = signature
            
            # 최종 쿼리 스트링 생성 (signature 포함, urlencode 사용)
            query_string = urlencode(params, doseq=True)
            url = f"{url}?{query_string}"
            
            # params는 None으로 설정 (이미 URL에 포함됨)
            params = None
        
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            # 바이낸스는 POST 요청도 쿼리 파라미터로 보냄
            resp = requests.post(url, headers=headers, params=params, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        resp.raise_for_status()
        response_json = resp.json()
        
        # 주문 응답 로깅
        if "/order" in path:
            logger.info(f"[BINANCE] 주문 응답: {json.dumps(response_json, indent=2)}")
        
        return response_json

    # ============================================
    # 시세 조회
    # ============================================
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """현재 시세 조회"""
        path = '/fapi/v1/ticker/price'
        params = {'symbol': symbol}
        return self._request("GET", path, params)

    def get_last_price(self, symbol: str) -> Decimal:
        """특정 상품의 현재 가격(마지막 체결가) 반환"""
        resp = self.get_ticker(symbol)
        if 'price' in resp:
            return Decimal(resp['price'])
        raise ValueError(f"가격 조회 실패: {symbol}")

    def get_price_info(self, symbol: str) -> Dict[str, Any]:
        """상세 가격 정보 조회"""
        path = '/fapi/v1/ticker/bookTicker'
        params = {'symbol': symbol}
        resp = self._request("GET", path, params)
        if 'bidPrice' in resp and 'askPrice' in resp:
            return {
                "last": float(resp.get('lastPrice', 0)),
                "bid": float(resp['bidPrice']),
                "ask": float(resp['askPrice']),
            }
        raise ValueError(f"가격 조회 실패: {symbol}")

    def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        """거래 상품 정보 조회 (lot size 등)"""
        path = '/fapi/v1/exchangeInfo'
        resp = self._request("GET", path)
        if 'symbols' in resp:
            for s in resp['symbols']:
                if s['symbol'] == symbol:
                    logger.info(f"[BINANCE] Exchange 정보 조회: symbol={symbol}, stepSize={s.get('filters', [{}])[0].get('stepSize', 'N/A')}")
                    return s
        raise ValueError(f"Exchange 정보 조회 실패: {symbol}")

    def round_to_step_size(self, quantity: str, symbol: str) -> str:
        """
        주문 수량을 step size의 배수로 반올림 (내림).
        
        Args:
            quantity: 주문 수량 (문자열)
            symbol: 거래 상품 (예: ETHUSDT)
        
        Returns:
            step size의 배수로 반올림된 수량 (문자열)
        """
        logger.info(f"[BINANCE] round_to_step_size 호출: quantity={quantity}, symbol={symbol}")
        try:
            # Exchange 정보에서 step size 가져오기
            logger.info(f"[BINANCE] Exchange 정보 조회 시작: {symbol}")
            exchange_info = self.get_exchange_info(symbol)
            
            # LOT_SIZE 필터에서 stepSize 찾기
            step_size = Decimal('0.001')  # 기본값
            min_qty = Decimal('0.001')  # 기본값
            
            for filter_item in exchange_info.get('filters', []):
                if filter_item.get('filterType') == 'LOT_SIZE':
                    step_size = Decimal(str(filter_item.get('stepSize', '0.001')))
                    min_qty = Decimal(str(filter_item.get('minQty', '0.001')))
                    break
            
            # 수량을 Decimal로 변환
            qty = Decimal(str(quantity))
            
            # 디버깅 로그
            logger.info(f"[BINANCE] Step size 반올림: 원본={qty}, step_size={step_size}, min_qty={min_qty}")
            
            # step size의 배수로 내림
            if step_size > 0:
                multiplier = (qty / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                rounded = multiplier * step_size
            else:
                rounded = qty
            
            # 최소 주문 수량 확인
            if rounded < min_qty:
                # min_qty를 step size의 배수로 올림
                if step_size > 0:
                    min_multiplier = (min_qty / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    if (min_qty / step_size) % 1 != 0:
                        min_multiplier += 1  # 올림
                    rounded = min_multiplier * step_size
                    logger.warning(f"[BINANCE] ⚠️ 반올림된 수량({rounded})이 최소 수량({min_qty})보다 작음, step size 배수로 조정: {rounded}")
                else:
                    rounded = min_qty
                    logger.warning(f"[BINANCE] ⚠️ 반올림된 수량({rounded})이 최소 수량({min_qty})보다 작음, 최소 수량 사용")
            
            logger.info(f"[BINANCE] ✅ Step size 반올림 결과: {qty} → {rounded} (step_size={step_size}, min_qty={min_qty}, 배수={multiplier if step_size > 0 else 'N/A'})")
            return str(rounded)
        except Exception as e:
            # 실패 시 기본값 0.001로 반올림
            import traceback
            logger.error(f"[BINANCE] ❌ Step size 반올림 실패, 기본값 사용: {e}\n{traceback.format_exc()}")
            qty = Decimal(str(quantity))
            step_size = Decimal('0.001')
            multiplier = (qty / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
            rounded = multiplier * step_size
            if rounded < Decimal('0.001'):
                rounded = Decimal('0.001')
            logger.info(f"[BINANCE] 기본값 사용 결과: {qty} → {rounded}")
            return str(rounded)

    # ============================================
    # 잔고 조회 (계좌 체크)
    # ============================================
    def get_balance(self) -> Dict[str, Any]:
        """계좌 잔고 조회"""
        path = '/fapi/v2/balance'
        return self._request("GET", path, signed=True)

    def get_account_info(self) -> Dict[str, Any]:
        """계좌 정보 조회 (잔고 포함)"""
        path = '/fapi/v2/account'
        return self._request("GET", path, signed=True)

    def get_usdt_balance(self) -> float:
        """USDT 사용 가능 잔고 반환"""
        resp = self.get_balance()
        if isinstance(resp, list):
            for asset in resp:
                if asset.get('asset') == 'USDT':
                    return float(asset.get('availableBalance', 0))
        return 0.0

    def calculate_order_size(
        self,
        symbol: str,
        leverage: int,
        balance_percent: float = 100.0,
    ) -> str:
        """
        잔고 기반으로 주문 수량 계산.
        
        Args:
            symbol: 거래 상품 (예: ETHUSDT)
            leverage: 레버리지 배수
            balance_percent: 사용할 잔고 비율 (기본값: 100%)
        
        Returns:
            계약 수량 (문자열)
        """
        # 1. USDT 잔고 조회
        usdt_balance = self.get_usdt_balance()
        if usdt_balance <= 0:
            raise ValueError("USDT 잔고가 없습니다")
        
        # 2. 사용할 금액 계산 (퍼센트 적용)
        available_margin = usdt_balance * (balance_percent / 100.0)
        
        # 3. 현재가 조회
        current_price = float(self.get_last_price(symbol))
        
        # 4. 레버리지 적용하여 주문 가능 계약 수 계산
        # 바이낸스 선물은 계약 단위가 아닌 수량 단위 사용
        # 주문 가능 금액 = 사용 가능 증거금 × 레버리지
        # 주문 수량 = 주문 가능 금액 / 현재가
        safety_margin = 0.97  # 안전 마진: 97%만 사용
        max_quantity = (available_margin * leverage * safety_margin) / current_price
        
        logger.info(f"[BINANCE] 수량 계산 상세: available_margin={available_margin:.2f}, leverage={leverage}, safety_margin={safety_margin}, current_price={current_price:.2f}")
        
        # 5. step size에 맞게 반올림
        quantity_str = str(max_quantity)
        logger.info(f"[BINANCE] 수량 계산: 잔고=${usdt_balance:.2f}, 현재가=${current_price:.2f}, 레버리지={leverage}x, 계산된 수량={max_quantity:.6f} (반올림 전)")
        
        try:
            quantity_rounded = self.round_to_step_size(quantity_str, symbol)
            quantity = float(quantity_rounded)
            
            if quantity <= 0:
                raise ValueError(
                    f"잔고 부족: USDT {usdt_balance:.2f}, "
                    f"계산된 수량이 0 이하입니다."
                )
            
            logger.info(f"[BINANCE] 수량 계산 완료: 최종 수량={quantity:.6f} (step size 반올림 후)")
            
            return quantity_rounded
        except Exception as e:
            import traceback
            logger.error(f"[BINANCE] ❌ 수량 계산 중 오류: {e}\n{traceback.format_exc()}")
            raise

    # ============================================
    # 레버리지 설정
    # ============================================
    def set_leverage(self, symbol: str, leverage: Optional[int] = None) -> Dict[str, Any]:
        """레버리지 설정"""
        path = '/fapi/v1/leverage'
        params = {
            'symbol': symbol,
            'leverage': leverage or self.leverage,
        }
        return self._request("POST", path, params, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> Dict[str, Any]:
        """마진 타입 설정 (ISOLATED 또는 CROSSED)"""
        path = '/fapi/v1/marginType'
        params = {
            'symbol': symbol,
            'marginType': margin_type,
        }
        return self._request("POST", path, params, signed=True)

    # ============================================
    # 포지션 조회
    # ============================================
    def get_positions(self) -> Dict[str, Any]:
        """포지션 조회"""
        path = '/fapi/v2/positionRisk'
        return self._request("GET", path, signed=True)

    def get_active_positions(self) -> List[Dict[str, Any]]:
        """활성 포지션만 반환"""
        resp = self.get_positions()
        if isinstance(resp, list):
            return [pos for pos in resp if float(pos.get('positionAmt', 0)) != 0]
        return []

    # ============================================
    # 시장가 주문
    # ============================================
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
    ) -> Dict[str, Any]:
        """시장가 주문"""
        path = '/fapi/v1/order'
        
        params = {
            'symbol': symbol,
            'side': side.upper(),  # BUY / SELL
            'type': 'MARKET',
            'quantity': quantity,
        }
        
        return self._request("POST", path, params, signed=True)

    def place_market_order_with_tp_sl(
        self,
        symbol: str,
        side: str,
        quantity: str,
        tp_percent: Optional[float] = None,
        sl_percent: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        TP(Take Profit)와 SL(Stop Loss)을 포함한 시장가 주문.
        바이낸스는 TP/SL을 별도 주문으로 생성해야 함.

        Args:
            symbol: 거래 상품 (예: ETHUSDT)
            side: "BUY" 또는 "SELL"
            quantity: 주문 수량
            tp_percent: 익절 퍼센트 (예: 2.3 = 2.3%)
            sl_percent: 손절 퍼센트 (예: 0.7 = 0.7%)

        Returns:
            바이낸스 API 응답
        """
        # 1. 메인 주문 실행
        main_order = self.place_market_order(symbol, side, quantity)
        
        if not self.is_success(main_order):
            return main_order
        
        # 2. TP/SL 주문 생성 (별도 주문)
        current_price = self.get_last_price(symbol)
        tp_order = None
        sl_order = None
        
        if tp_percent is not None:
            # TP 가격 계산
            if side.upper() == "BUY":
                tp_price = current_price * (1 + Decimal(str(tp_percent)) / 100)
            else:  # SELL
                tp_price = current_price * (1 - Decimal(str(tp_percent)) / 100)
            
            # TP 주문 (TAKE_PROFIT_MARKET)
            try:
                tp_order = self.place_take_profit_order(
                    symbol=symbol,
                    side="SELL" if side.upper() == "BUY" else "BUY",
                    quantity=quantity,
                    stop_price=str(tp_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN)),
                )
                logger.info(f"[BINANCE] ✅ TP 주문 생성: {current_price} → {tp_price} (+{tp_percent}%)")
            except Exception as e:
                logger.error(f"[BINANCE] ❌ TP 주문 생성 실패: {e}")
        
        if sl_percent is not None:
            # SL 가격 계산
            if side.upper() == "BUY":
                sl_price = current_price * (1 - Decimal(str(sl_percent)) / 100)
            else:  # SELL
                sl_price = current_price * (1 + Decimal(str(sl_percent)) / 100)
            
            # SL 주문 (STOP_MARKET)
            try:
                sl_order = self.place_stop_loss_order(
                    symbol=symbol,
                    side="SELL" if side.upper() == "BUY" else "BUY",
                    quantity=quantity,
                    stop_price=str(sl_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN)),
                )
                logger.info(f"[BINANCE] ✅ SL 주문 생성: {current_price} → {sl_price} (-{sl_percent}%)")
            except Exception as e:
                logger.error(f"[BINANCE] ❌ SL 주문 생성 실패: {e}")
        
        # 메인 주문과 TP/SL 주문 정보 반환
        return {
            "main_order": main_order,
            "tp_order": tp_order,
            "sl_order": sl_order,
        }

    def place_take_profit_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        stop_price: str,
    ) -> Dict[str, Any]:
        """Take Profit 주문 생성"""
        path = '/fapi/v1/order'
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'TAKE_PROFIT_MARKET',
            'quantity': quantity,
            'stopPrice': stop_price,
            'closePosition': 'false',
        }
        return self._request("POST", path, params, signed=True)

    def place_stop_loss_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        stop_price: str,
    ) -> Dict[str, Any]:
        """Stop Loss 주문 생성"""
        path = '/fapi/v1/order'
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'STOP_MARKET',
            'quantity': quantity,
            'stopPrice': stop_price,
            'closePosition': 'false',
        }
        return self._request("POST", path, params, signed=True)

    # ============================================
    # 주문 관련 유틸리티
    # ============================================
    def place_order_with_leverage(
        self,
        symbol: str,
        side: str,
        quantity: str,
        leverage: Optional[int] = None,
        tp_percent: Optional[float] = None,
        sl_percent: Optional[float] = None,
        margin_type: str = "CROSSED",
    ) -> Dict[str, Any]:
        """
        레버리지 설정 후 TP/SL 포함 주문.
        자동매매에서 주로 사용하는 통합 메서드.
        """
        logger.info(f"[BINANCE] place_order_with_leverage 호출: symbol={symbol}, side={side}, quantity={quantity}, leverage={leverage}, tp={tp_percent}, sl={sl_percent}")
        
        # 1. 레버리지 설정
        lev = leverage or self.leverage
        
        try:
            self.set_leverage(symbol, lev)
        except Exception as e:
            # 레버리지 설정 실패해도 주문은 진행 (이미 설정되어 있을 수 있음)
            logger.warning(f"[BINANCE] 레버리지 설정 경고: {e}")
        
        # 2. 마진 타입 설정
        try:
            self.set_margin_type(symbol, margin_type)
        except Exception as e:
            # 마진 타입 설정 실패해도 주문은 진행 (이미 설정되어 있을 수 있음)
            logger.warning(f"[BINANCE] 마진 타입 설정 경고: {e}")
        
        # 3. 주문 수량을 step size에 맞게 반올림
        logger.info(f"[BINANCE] 주문 수량 반올림 시작: 원본={quantity}, symbol={symbol}")
        try:
            quantity_rounded = self.round_to_step_size(quantity, symbol)
            logger.info(f"[BINANCE] 주문 수량 반올림 완료: {quantity} → {quantity_rounded}")
        except Exception as e:
            import traceback
            logger.error(f"[BINANCE] ⚠️ 주문 수량 반올림 실패: {e}, 원본 수량 사용\n{traceback.format_exc()}")
            quantity_rounded = quantity  # 실패 시 원본 사용
        
        # 4. 주문 실행
        if tp_percent is not None or sl_percent is not None:
            return self.place_market_order_with_tp_sl(
                symbol=symbol,
                side=side,
                quantity=quantity_rounded,
                tp_percent=tp_percent,
                sl_percent=sl_percent,
            )
        else:
            return self.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity_rounded,
            )

    # ============================================
    # 결과 확인 유틸리티
    # ============================================
    @staticmethod
    def is_success(resp: Dict[str, Any]) -> bool:
        """API 응답이 성공인지 확인"""
        # 바이낸스는 주문 성공 시 orderId를 반환
        # TP/SL이 포함된 경우 main_order에 orderId가 있음
        if 'main_order' in resp:
            main_order = resp['main_order']
            return 'orderId' in main_order and 'code' not in main_order
        # 일반 주문의 경우
        return 'orderId' in resp and 'code' not in resp

    @staticmethod
    def get_order_id(resp: Dict[str, Any]) -> Optional[str]:
        """응답에서 주문 ID 추출"""
        # TP/SL이 포함된 경우
        if 'main_order' in resp and 'orderId' in resp['main_order']:
            return str(resp['main_order']['orderId'])
        # 일반 주문의 경우
        if 'orderId' in resp:
            return str(resp['orderId'])
        return None

    @staticmethod
    def get_error_message(resp: Dict[str, Any]) -> str:
        """응답에서 에러 메시지 추출"""
        # TP/SL이 포함된 경우 main_order에서 에러 확인
        if 'main_order' in resp:
            main_order = resp['main_order']
            if 'msg' in main_order:
                return main_order['msg']
            if 'code' in main_order:
                return f"Error code: {main_order['code']}"
        # 일반 주문의 경우
        if 'msg' in resp:
            return resp['msg']
        if 'code' in resp:
            return f"Error code: {resp['code']}"
        return 'Unknown error'
    
    @classmethod
    def from_config(cls, config: Optional['BinanceConfig'] = None) -> 'BinanceClient':
        """
        config_binance.json 설정에서 BinanceClient 인스턴스 생성.
        
        Args:
            config: BinanceConfig 인스턴스. None이면 자동으로 로드.
        
        Returns:
            BinanceClient 인스턴스
        """
        if config is None:
            from .config import get_binance_config
            config = get_binance_config()
        
        account = config.get_account()
        return cls(
            api_key=config.api_key,
            secret_key=config.secret_key,
            is_testnet=config.is_account_testnet(account),
            leverage=config.trading_leverage,
            base_url=config.base_url,
        )
    
    @classmethod
    def from_account_config(cls, account_config: Dict[str, Any], trading_config: Dict[str, Any], global_config: Optional['BinanceConfig'] = None) -> 'BinanceClient':
        """
        계정 설정 딕셔너리에서 BinanceClient 인스턴스 생성.
        
        Args:
            account_config: 계정 정보 딕셔너리 (api_key, secret_key, leverage, base_url, testnet 등)
            trading_config: 트레이딩 설정 딕셔너리 (기본 leverage 등)
            global_config: BinanceConfig 인스턴스 (전역 testnet 설정 확인용). None이면 자동으로 로드.
        
        Returns:
            BinanceClient 인스턴스
        """
        # testnet 설정 확인: 계정별 설정 우선, 없으면 전역 설정 사용
        is_testnet = False
        if global_config is None:
            from .config import get_binance_config
            global_config = get_binance_config()
        
        is_testnet = global_config.is_account_testnet(account_config)
        
        return cls(
            api_key=account_config.get("api_key", ""),
            secret_key=account_config.get("secret_key", ""),
            is_testnet=is_testnet,
            leverage=account_config.get("leverage", trading_config.get("leverage", 10)),
            base_url=account_config.get("base_url", "https://fapi.binance.com"),
        )

