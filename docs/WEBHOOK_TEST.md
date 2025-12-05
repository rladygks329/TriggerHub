# 웹훅 테스트 가이드

## 엔드포인트

- **로컬**: `http://127.0.0.1:8000/webhook/okx/`
- **배포 서버**: `https://your-domain.com/webhook/okx/`

## 요청 형식

- **Method**: POST
- **Content-Type**: application/json

## 필수 필드

- `symbol` 또는 `instId`: 거래 심볼 (예: "BTC-USDT-SWAP", "ETH-USDT-SWAP")
- `side` 또는 `action`: "buy" 또는 "sell"
- `size` 또는 `qty`: 주문 수량 (문자열, 예: "1", "0.01")
- `secret`: 선택사항 (WEBHOOK_SECRET 환경변수가 설정되어 있으면 필수)

---

## Windows PowerShell에서 테스트

### 1. 기본 테스트 (시크릿 없이)

```powershell
curl -Method POST `
  -Uri "http://127.0.0.1:8000/webhook/okx/" `
  -ContentType "application/json" `
  -Body '{"symbol":"BTC-USDT-SWAP","side":"buy","size":"1"}'
```

### 2. 시크릿 포함 테스트

```powershell
curl -Method POST `
  -Uri "http://127.0.0.1:8000/webhook/okx/" `
  -ContentType "application/json" `
  -Body '{"secret":"your-webhook-secret","symbol":"BTC-USDT-SWAP","side":"buy","size":"1"}'
```

### 3. 매도 주문 테스트

```powershell
curl -Method POST `
  -Uri "http://127.0.0.1:8000/webhook/okx/" `
  -ContentType "application/json" `
  -Body '{"symbol":"BTC-USDT-SWAP","side":"sell","size":"1"}'
```

### 4. JSON 파일로 테스트 (긴 요청용)

`test-webhook.json` 파일 생성:

```json
{
  "secret": "your-webhook-secret",
  "symbol": "BTC-USDT-SWAP",
  "side": "buy",
  "size": "1"
}
```

명령어:

```powershell
curl -Method POST `
  -Uri "http://127.0.0.1:8000/webhook/okx/" `
  -ContentType "application/json" `
  -InFile test-webhook.json
```

---

## Linux/Mac/Git Bash에서 테스트

### 1. 기본 테스트

```bash
curl -X POST \
  http://127.0.0.1:8000/webhook/okx/ \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC-USDT-SWAP","side":"buy","size":"1"}'
```

### 2. 시크릿 포함

```bash
curl -X POST \
  http://127.0.0.1:8000/webhook/okx/ \
  -H "Content-Type: application/json" \
  -d '{"secret":"your-webhook-secret","symbol":"BTC-USDT-SWAP","side":"buy","size":"1"}'
```

### 3. 매도 주문

```bash
curl -X POST \
  http://127.0.0.1:8000/webhook/okx/ \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC-USDT-SWAP","side":"sell","size":"1"}'
```

### 4. JSON 파일 사용

```bash
curl -X POST \
  http://127.0.0.1:8000/webhook/okx/ \
  -H "Content-Type: application/json" \
  -d @test-webhook.json
```

---

## TradingView Webhook 설정 예시

TradingView Alert에서 Webhook URL 설정:

```
http://your-server.com/webhook/okx/
```

Webhook Message (JSON):

```json
{
  "secret": "your-webhook-secret",
  "symbol": "{{ticker}}",
  "side": "{{strategy.order.action}}",
  "size": "1"
}
```

또는 더 간단하게:

```json
{
  "secret": "your-webhook-secret",
  "instId": "{{ticker}}-USDT-SWAP",
  "action": "{{strategy.order.action}}",
  "qty": "1"
}
```

---

## 응답 예시

### 성공 응답

```json
{
  "ok": true,
  "order_id": "123456789",
  "log_id": 1
}
```

### 에러 응답

```json
{
  "ok": false,
  "error": "invalid_secret",
  "log_id": 1
}
```

---

## 주의사항

1. **모의거래 모드**: 현재 코드는 기본적으로 모의거래 모드로 설정되어 있습니다 (`x-simulated-trading: 1`).

   - 실거래를 하려면 `trading/okx_client.py`의 `_headers` 메서드에서 해당 헤더를 제거하세요.

2. **환경변수 설정**: 서버 실행 전에 다음 환경변수를 설정해야 합니다:

   ```powershell
   $env:OKX_API_KEY = "your-api-key"
   $env:OKX_SECRET_KEY = "your-secret-key"
   $env:OKX_PASSPHRASE = "your-passphrase"
   $env:WEBHOOK_SECRET = "your-webhook-secret"  # 선택사항
   ```

3. **심볼 형식**: OKX 심볼 형식에 맞춰야 합니다:

   - 선물: `BTC-USDT-SWAP`, `ETH-USDT-SWAP`
   - 현물: `BTC-USDT`, `ETH-USDT`

4. **테스트 순서**:
   - 먼저 로컬에서 테스트
   - 모의거래로 실제 OKX API 호출 확인
   - 문제없으면 서버 배포 후 TradingView 연동
