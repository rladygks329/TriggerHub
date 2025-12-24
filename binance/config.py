"""
바이낸스 설정 파일 로더 모듈
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# 로거 설정
logger = logging.getLogger(__name__)


class BinanceConfig:
    """바이낸스 설정 관리 클래스"""
    
    _instance: Optional['BinanceConfig'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _find_config_file(self) -> Path:
        """config_binance.json 파일 경로 찾기"""
        # 1. 환경 변수에서 지정된 경로
        env_path = os.getenv("BINANCE_CONFIG_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)
        
        # 2. 프로젝트 루트 (manage.py가 있는 위치)
        current_dir = Path(__file__).resolve().parent.parent
        config_path = current_dir / "config_binance.json"
        if config_path.exists():
            return config_path
        
        # 3. 현재 작업 디렉토리
        cwd_config = Path.cwd() / "config_binance.json"
        if cwd_config.exists():
            return cwd_config
        
        raise FileNotFoundError(
            "config_binance.json 파일을 찾을 수 없습니다. "
            "프로젝트 루트에 config_binance.json 파일을 생성하거나 "
            "BINANCE_CONFIG_PATH 환경 변수를 설정하세요."
        )
    
    def _load_config(self) -> None:
        """설정 파일 로드"""
        try:
            config_path = self._find_config_file()
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            logger.info(f"✅ config_binance.json 로드 완료: {config_path}")
        except FileNotFoundError as e:
            logger.error(f"❌ {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"❌ config_binance.json 파일 형식이 올바르지 않습니다: {e}")
            raise
    
    def reload(self) -> None:
        """설정 다시 로드"""
        self._load_config()
    
    # ============================================
    # 계정 관리 (여러 계정 지원)
    # ============================================
    @property
    def accounts(self) -> List[Dict[str, Any]]:
        """모든 계정 목록"""
        accounts = self._config.get("accounts", [])
        # 하위 호환성: 기존 api_key 등이 있으면 accounts 배열로 변환
        if not accounts and self._config.get("api_key"):
            return [{
                "name": "default",
                "api_key": self._config.get("api_key", ""),
                "secret_key": self._config.get("secret_key", ""),
                "base_url": self._config.get("base_url", "https://fapi.binance.com"),
                "testnet": self._config.get("testnet", False),
                "useYn": "y",  # 기본값은 활성화
            }]
        return accounts
    
    def get_active_accounts(self) -> List[Dict[str, Any]]:
        """
        활성화된 계정만 반환 (useYn이 "y"인 계정)
        
        Returns:
            활성화된 계정 목록
        """
        return [
            account for account in self.accounts
            if account.get("useYn", "y").lower() == "y"
        ]
    
    def get_account(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        특정 계정 정보 가져오기
        
        Args:
            name: 계정 이름. None이면 첫 번째 계정 또는 기본 계정 반환
        
        Returns:
            계정 정보 딕셔너리
        """
        accounts = self.accounts
        if not accounts:
            raise ValueError("설정에 계정이 없습니다. accounts 배열을 확인하세요.")
        
        if name:
            # 이름으로 찾기
            for account in accounts:
                if account.get("name") == name:
                    return account
            raise ValueError(f"계정 '{name}'을 찾을 수 없습니다.")
        else:
            # 기본 계정 (첫 번째 또는 name이 "default"인 것)
            for account in accounts:
                if account.get("name") == "default":
                    return account
            return accounts[0]  # 첫 번째 계정 반환
    
    def get_account_names(self) -> List[str]:
        """모든 계정 이름 목록"""
        return [acc.get("name", f"account_{i}") for i, acc in enumerate(self.accounts)]
    
    # ============================================
    # API 설정 (하위 호환성 - 기본 계정 사용)
    # ============================================
    @property
    def api_key(self) -> str:
        """기본 계정의 API 키 (하위 호환성)"""
        try:
            return self.get_account().get("api_key", "")
        except (ValueError, IndexError):
            return self._config.get("api_key", "")
    
    @property
    def secret_key(self) -> str:
        """기본 계정의 Secret 키 (하위 호환성)"""
        try:
            return self.get_account().get("secret_key", "")
        except (ValueError, IndexError):
            return self._config.get("secret_key", "")
    
    @property
    def base_url(self) -> str:
        """기본 계정의 Base URL (하위 호환성)"""
        try:
            return self.get_account().get("base_url", "https://fapi.binance.com")
        except (ValueError, IndexError):
            return self._config.get("base_url", "https://fapi.binance.com")
    
    @property
    def testnet(self) -> bool:
        """전역 Testnet 모드 여부 (config_binance.json의 testnet 필드)"""
        testnet_value = self._config.get("testnet", False)
        return bool(testnet_value)
    
    def is_account_testnet(self, account: Optional[Dict[str, Any]] = None) -> bool:
        """
        계정별 Testnet 모드 여부
        
        Args:
            account: 계정 정보 딕셔너리. None이면 기본 계정 사용
        
        Returns:
            계정의 testnet 설정이 True이면 True, 아니면 전역 testnet 설정 사용
        """
        if account is None:
            account = self.get_account()
        
        # 계정별 testnet 설정이 있으면 우선 사용
        account_testnet = account.get("testnet")
        if account_testnet is not None:
            return bool(account_testnet)
        
        # 계정별 설정이 없으면 전역 testnet 설정 사용
        return self.testnet
    
    # ============================================
    # 기본 거래 설정
    # ============================================
    @property
    def leverage(self) -> int:
        return int(self._config.get("leverage", 10))
    
    # ============================================
    # 웹훅 설정
    # ============================================
    @property
    def webhook_secret(self) -> str:
        return self._config.get("webhook_secret", "")
    
    # ============================================
    # 트레이딩 설정
    # ============================================
    @property
    def trading(self) -> Dict[str, Any]:
        return self._config.get("trading", {})
    
    @property
    def trading_symbol(self) -> str:
        return self.trading.get("symbol", "ETHUSDT")
    
    @property
    def trading_leverage(self) -> int:
        return int(self.trading.get("leverage", self.leverage))
    
    @property
    def use_full_balance(self) -> bool:
        return self.trading.get("use_full_balance", False)
    
    @property
    def stop_loss_percent(self) -> float:
        return float(self.trading.get("stop_loss_percent", 0.7))
    
    @property
    def take_profit_percent(self) -> float:
        return float(self.trading.get("take_profit_percent", 2.3))
    
    @property
    def enable_trading(self) -> bool:
        return self.trading.get("enable_trading", True)
    
    # ============================================
    # 전체 설정 접근
    # ============================================
    def get(self, key: str, default: Any = None) -> Any:
        """키로 설정값 가져오기"""
        return self._config.get(key, default)
    
    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """중첩된 키로 설정값 가져오기"""
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """전체 설정을 딕셔너리로 반환 (민감 정보 마스킹)"""
        config_copy = self._config.copy()
        
        # accounts 배열의 민감 정보 마스킹
        if "accounts" in config_copy and isinstance(config_copy["accounts"], list):
            for account in config_copy["accounts"]:
                for key in ["api_key", "secret_key"]:
                    if key in account and account[key]:
                        account[key] = "***" + account[key][-4:] if len(account[key]) > 4 else "****"
        
        # 기존 형식의 민감 정보 마스킹 (하위 호환성)
        for key in ["api_key", "secret_key", "webhook_secret"]:
            if key in config_copy and config_copy[key]:
                config_copy[key] = "***" + config_copy[key][-4:] if len(config_copy[key]) > 4 else "****"
        
        return config_copy
    
    def __repr__(self) -> str:
        return f"<BinanceConfig: {self.to_dict()}>"


# 싱글톤 인스턴스 (lazy loading)
def get_binance_config() -> BinanceConfig:
    """바이낸스 설정 인스턴스 가져오기"""
    return BinanceConfig()

