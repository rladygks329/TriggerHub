"""
설정 파일 로더 모듈
config.json에서 설정을 읽어옵니다.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """설정 관리 클래스"""
    
    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _find_config_file(self) -> Path:
        """config.json 파일 경로 찾기"""
        # 1. 환경 변수에서 지정된 경로
        env_path = os.getenv("CONFIG_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)
        
        # 2. 프로젝트 루트 (manage.py가 있는 위치)
        current_dir = Path(__file__).resolve().parent.parent
        config_path = current_dir / "config.json"
        if config_path.exists():
            return config_path
        
        # 3. 현재 작업 디렉토리
        cwd_config = Path.cwd() / "config.json"
        if cwd_config.exists():
            return cwd_config
        
        raise FileNotFoundError(
            "config.json 파일을 찾을 수 없습니다. "
            "프로젝트 루트에 config.json 파일을 생성하거나 "
            "CONFIG_PATH 환경 변수를 설정하세요."
        )
    
    def _load_config(self) -> None:
        """설정 파일 로드"""
        try:
            config_path = self._find_config_file()
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            print(f"✅ config.json 로드 완료: {config_path}")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ config.json 파일 형식이 올바르지 않습니다: {e}")
            raise
    
    def reload(self) -> None:
        """설정 다시 로드"""
        self._load_config()
    
    # ============================================
    # API 설정
    # ============================================
    @property
    def api_key(self) -> str:
        return self._config.get("api_key", "")
    
    @property
    def secret_key(self) -> str:
        return self._config.get("secret_key", "")
    
    @property
    def passphrase(self) -> str:
        return self._config.get("passphrase", "")
    
    @property
    def base_url(self) -> str:
        return self._config.get("base_url", "https://www.okx.com")
    
    @property
    def is_demo(self) -> bool:
        return self._config.get("is_demo", False)
    
    # ============================================
    # 기본 거래 설정
    # ============================================
    @property
    def td_mode(self) -> str:
        return self._config.get("td_mode", "cross")
    
    @property
    def leverage(self) -> int:
        return int(self._config.get("leverage", 10))
    
    # ============================================
    # 웹훅 설정
    # ============================================
    @property
    def webhook_secret(self) -> str:
        return self._config.get("webhook_secret", "")
    
    @property
    def webhook_port(self) -> int:
        return int(self._config.get("webhook_port", 8000))
    
    # ============================================
    # 트레이딩 설정
    # ============================================
    @property
    def trading(self) -> Dict[str, Any]:
        return self._config.get("trading", {})
    
    @property
    def trading_symbol(self) -> str:
        return self.trading.get("symbol", "BTC-USDT-SWAP")
    
    @property
    def trading_leverage(self) -> int:
        return int(self.trading.get("leverage", self.leverage))
    
    @property
    def trading_td_mode(self) -> str:
        return self.trading.get("td_mode", self.td_mode)
    
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
        # 민감 정보 마스킹
        for key in ["api_key", "secret_key", "passphrase", "webhook_secret"]:
            if key in config_copy and config_copy[key]:
                config_copy[key] = "***" + config_copy[key][-4:] if len(config_copy[key]) > 4 else "****"
        return config_copy
    
    def __repr__(self) -> str:
        return f"<Config: {self.to_dict()}>"


# 싱글톤 인스턴스 (lazy loading)
def get_config() -> Config:
    """설정 인스턴스 가져오기"""
    return Config()

