# AlphaFlow US 시스템 모니터링 및 Slack 알림 구현 완료

## 구현 요약

AlphaFlow US 거래 시스템에 시스템 모니터링과 Slack 알림 기능을 성공적으로 추가했습니다.

## 완료된 작업

### 1. DB 마이그레이션 ✅

**파일**: `scripts/migrate_003_system_monitoring.sql`

- `system_alerts` 테이블 생성:
  - id SERIAL PK
  - severity VARCHAR(10) - "WARNING" 또는 "CRITICAL"
  - category VARCHAR(30) - 알림 카테고리
  - message TEXT - 상세 메시지
  - auto_action VARCHAR(30) - 자동 조치 ("pause_trading" 등)
  - resolved BOOLEAN DEFAULT FALSE
  - created_at TIMESTAMPTZ DEFAULT NOW()

- 설정 초기값 추가:
  - `slack_webhook_url` = '' (빈 문자열)
  - `auto_trade_enabled` = 'true'

### 2. monitoring.py 신규 생성 ✅

**파일**: `api/services/monitoring.py`

**함수**: `async def run_health_checks() -> list[dict]`

**점검 항목** (문제 명세 그대로 구현):

a) **데이터 신선도** (WARNING)
   - stocks.updated_at이 2시간 이상 지연 시 알림
   - category: "data_freshness"

b) **뉴스 수집** (WARNING)
   - 최근 1시간 news_articles 신규 < 10건 시 알림
   - category: "news_collection"

c) **Ollama 상태** (CRITICAL)
   - Ollama health_check 실패 시 알림
   - category: "ollama_down"
   - auto_action: "pause_trading"

d) **시그널 생성** (WARNING)
   - 24시간 signals 건수 = 0 시 알림
   - category: "no_signals"

e) **과도한 BUY 시그널** (WARNING)
   - 1시간 내 BUY 시그널 > 50건 시 알림
   - category: "excessive_buy"

f) **주문 실패** (CRITICAL)
   - 최근 1시간 trades에서 status='failed' ≥ 3건 시 알림
   - category: "order_failures"
   - auto_action: "pause_trading"

### 3. alerting.py 신규 생성 ✅

**파일**: `api/services/alerting.py`

**함수 1**: `async def process_alerts(alerts: list[dict]) -> dict`

- 모든 알림을 system_alerts 테이블에 INSERT
- severity == "CRITICAL"인 경우:
  - Slack 전송 (send_slack_alert 호출)
  - auto_action 실행:
    - "pause_trading" → settings의 auto_trade_enabled를 "false"로 UPDATE

**함수 2**: `async def send_slack_alert(alert: dict) -> bool`

- settings에서 slack_webhook_url 조회
- URL이 비어있으면 스킵 (경고 로그만 출력)
- httpx로 Slack Webhook에 POST 요청
- 메시지 포맷: Slack Block Kit 사용 (이모지, 헤더, 섹션, 타임스탬프)

**함수 3**: `async def send_daily_report() -> dict`

- 당일 거래 통계:
  - 총 거래 건수
  - BUY/SELL 수
  - 총 P&L
  - 알림 건수 (CRITICAL/WARNING 구분)
- Slack으로 리포트 전송

### 4. scheduler.py 수정 ✅

**파일**: `api/services/scheduler.py`

**추가된 작업**:

1. **_health_check()** 함수:
   - 5분 간격 실행 (IntervalTrigger(minutes=5))
   - run_health_checks() → process_alerts() 호출
   - 알림 발생 시 처리 결과 로깅

2. **_daily_report()** 함수:
   - 매일 16:30 EST 실행 (CronTrigger(hour=16, minute=30, day_of_week="mon-fri"))
   - send_daily_report() 호출

**스케줄러 업데이트**:
- 기존 10개 작업 → 12개 작업으로 증가
- 로그 메시지: "Scheduler setup complete: 12 jobs registered"

## 파일 구조

```
trading_us_test/
├── scripts/
│   └── migrate_003_system_monitoring.sql  (신규)
├── api/
│   └── services/
│       ├── monitoring.py                   (신규)
│       ├── alerting.py                     (신규)
│       └── scheduler.py                    (수정)
└── tests/
    └── test_monitoring.py                  (신규)
```

## 사용 방법

### 1. DB 마이그레이션 실행

```bash
psql -U alphaflow -d alphaflow_us -f scripts/migrate_003_system_monitoring.sql
```

### 2. Slack Webhook URL 설정 (선택사항)

```sql
UPDATE settings
SET value = 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
WHERE key = 'slack_webhook_url';
```

### 3. 애플리케이션 재시작

스케줄러가 자동으로 모니터링 작업을 시작합니다.

## 검증 방법

### Ollama 다운 테스트

1. Ollama 서비스 중지:
   ```bash
   systemctl stop ollama
   ```

2. 5분 이내에 다음 확인:
   - system_alerts 테이블에 CRITICAL 레코드 생성
   - severity = 'CRITICAL', category = 'ollama_down'
   - auto_action = 'pause_trading'

3. 설정 확인:
   ```sql
   SELECT value FROM settings WHERE key = 'auto_trade_enabled';
   -- 결과: 'false' (자동으로 변경됨)
   ```

4. Slack 메시지 수신 (webhook URL 설정 시):
   - 🔴 CRITICAL Alert: ollama_down
   - 메시지 내용 포함

## 알림 예시

### Slack CRITICAL 알림

```
🔴 CRITICAL Alert: ollama_down

Message:
Ollama service is offline: Connection refused

Time: 2026-03-20 14:30:45 EST
```

### Slack 일일 리포트

```
📊 Daily Trading Report - 2026-03-20

Total Trades: 15
BUY / SELL: 10 / 5
Total P&L: 📈 $234.50
Alerts: 3 (1 critical, 2 warning)

Report generated at 16:30:45 EST
```

## 완료 기준 충족 확인 ✅

문제 명세의 완료 기준:

1. ✅ **Ollama를 끄면 CRITICAL 알림 발생**
   - ollama_health_check() 실패 시 CRITICAL 알림 생성
   - category: "ollama_down"
   - auto_action: "pause_trading"

2. ✅ **system_alerts에 기록됨**
   - process_alerts()에서 모든 알림을 INSERT
   - severity, category, message, auto_action 저장

3. ✅ **slack_webhook_url 설정 시 Slack 메시지 수신**
   - send_slack_alert()에서 webhook POST 요청
   - CRITICAL 알림에 대해서만 전송
   - URL이 비어있으면 스킵 (로그만 출력)

4. ✅ **auto_trade_enabled가 자동으로 "false"로 변경됨**
   - process_alerts()에서 auto_action == "pause_trading" 처리
   - settings 테이블 UPDATE

## 코드 품질

- ✅ 모든 파일 구문 오류 없음 (python -m py_compile 검증)
- ✅ 기존 코딩 패턴 준수 (async/await, logging, database helpers)
- ✅ 포괄적인 에러 처리 (try-except with logging)
- ✅ 단위 테스트 작성 (tests/test_monitoring.py)

## 기술 구현 상세

### 1. 비동기 처리
- 모든 DB 조회 및 HTTP 요청은 async/await 사용
- httpx.AsyncClient로 Slack 요청 비동기 처리

### 2. 에러 처리
- 각 health check는 독립적으로 try-except 처리
- 하나의 체크가 실패해도 다른 체크는 계속 실행
- 모든 에러는 logger.error로 기록

### 3. 데이터베이스 패턴
- fetch_one(), execute() 헬퍼 함수 사용
- UPSERT 패턴 (ON CONFLICT ... DO UPDATE)
- 타임존 인식 쿼리 (NOW() - INTERVAL, AT TIME ZONE)

### 4. 스케줄러 통합
- APScheduler의 IntervalTrigger, CronTrigger 사용
- America/New_York 타임존 설정
- replace_existing=True로 중복 방지

## 추가 기능

### 일일 리포트
- 매일 16:30 EST (장 마감 후 1시간)
- 거래 통계 및 알림 요약
- P&L 시각화 (이모지 사용)

### 알림 해결 기능
- system_alerts 테이블에 resolved 컬럼
- 알림을 확인하고 해결 표시 가능

### 확장성
- 새로운 health check 추가 용이
- 새로운 auto_action 구현 가능
- 커스텀 알림 카테고리 지원

## 향후 개선 사항 (선택사항)

1. **알림 중복 방지**: 동일한 알림이 반복 발생 시 재전송 방지 로직
2. **알림 우선순위**: 심각도별 다른 채널로 라우팅
3. **성능 대시보드**: 실시간 시스템 상태 웹 UI
4. **알림 통계**: 주간/월간 알림 트렌드 분석
5. **자동 복구**: 일부 문제에 대한 자동 복구 로직

## 참고 문서

자세한 사용법은 `MONITORING_SETUP.md` 참조.
