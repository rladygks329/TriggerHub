## TriggerHub - Django OKX Auto Trading Webhook

이 프로젝트는 Django 기반으로 동작하는 간단한 OKX 자동매매 웹훅 서버 뼈대입니다.

- **기술 스택**: Python, Django, SQLite, requests
- **기능**:
  - 외부에서 오는 **Webhook**(예: 트레이딩뷰) 수신
  - 시그널을 파싱해서 **OKX API**로 시장가 주문 전송
  - 요청/응답 내용을 `TradeLog` 모델에 저장

### 1. 초기 설정

```bash
python -m venv venv
venv\Scripts\activate  # Windows 기준
pip install -r requirements.txt
python manage.py migrate
```

### 2. 환경 변수 설정

아래 값들을 OS 환경 변수 또는 `.env`(원하시면 dotenv 추가 가능)에 등록해야 합니다.

- `OKX_API_KEY`
- `OKX_SECRET_KEY`
- `OKX_PASSPHRASE`
- (선택) `WEBHOOK_SECRET` – Webhook 호출 시 함께 넘기는 시크릿 값

### 3. 서버 실행

```bash
python manage.py runserver 0.0.0.0:8000
```

웹훅 엔드포인트:

- `POST /webhook/okx/`

요청 예시(JSON, 매우 단순화된 예):

```json
{
  "secret": "YOUR_WEBHOOK_SECRET",
  "symbol": "BTC-USDT-SWAP",
  "side": "buy",
  "size": "1"
}
```

### 4. 주의사항

- 이 코드는 **실거래 이전에 반드시 모의/테스트 환경에서 충분히 검증**해야 합니다.
- OKX API 스펙/제한/리스크 관리(레버리지, 포지션, 마진 등)는 반드시 문서를 참고해서 보완하세요.


