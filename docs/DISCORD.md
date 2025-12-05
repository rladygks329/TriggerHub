# Discord 연동 가이드

## 1. Discord 웹훅 생성

1. Discord 서버에서 알림을 받을 채널 선택
2. 채널 설정 (톱니바퀴 아이콘) → 연동 → 웹후크
3. "새 웹후크 만들기" 클릭
4. 웹후크 이름 설정 (예: "TriggerHub 알림")
5. "웹후크 URL 복사" 클릭

## 2. 환경변수 설정

`.env` 파일에 Discord 웹훅 URL 추가:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxx/xxxxx
```

또는 EC2에서:

```bash
nano .env
# DISCORD_WEBHOOK_URL=your-webhook-url 추가
```

## 3. 기능

### 자동 알림

거래 주문이 실행될 때마다 Discord로 자동 알림이 전송됩니다:

- ✅ **주문 성공**: 초록색 임베드
  - 심볼, 방향, 수량, 주문 ID 표시
  
- ❌ **주문 실패**: 빨간색 임베드
  - 심볼, 방향, 수량, 에러 메시지 표시

### 알림 내용

- **제목**: 주문 성공/실패 상태
- **심볼**: 거래 심볼 (예: BTC-USDT-SWAP)
- **방향**: BUY 또는 SELL
- **수량**: 주문 수량
- **주문 ID**: OKX 주문 ID (성공 시)
- **에러**: 에러 메시지 (실패 시)

## 4. 테스트

### 수동 테스트

```python
# Python에서 테스트
from trading.discord import send_trade_notification, get_discord_webhook_url

webhook_url = get_discord_webhook_url()
if webhook_url:
    send_trade_notification(
        webhook_url=webhook_url,
        symbol="BTC-USDT-SWAP",
        side="buy",
        size="1",
        order_id="123456789",
        status="success",
    )
```

### 실제 거래로 테스트

웹훅을 통해 주문을 실행하면 자동으로 Discord 알림이 전송됩니다.

## 5. Discord 알림 비활성화

`.env` 파일에서 `DISCORD_WEBHOOK_URL`을 제거하거나 주석 처리:

```env
# DISCORD_WEBHOOK_URL=
```

## 6. 커스터마이징

`trading/discord.py` 파일을 수정하여 알림 형식을 변경할 수 있습니다:

- 색상 변경
- 필드 추가/제거
- 임베드 형식 변경

