# 백테스트 리포트 시스템 사용 가이드

## 개요

AlphaFlow US 백테스트 결과를 자동으로 분석하고 진단하는 리포트 시스템입니다.

## 주요 기능

### 1. 자동 리포트 생성 (`generate_report`)

백테스트 결과를 종합 분석하여 다음 지표를 자동 계산:

#### 수익률 지표
- `total_return_pct`: 총 수익률 (%)
- `annualized_return_pct`: 연율화 수익률 (252일 기준)

#### 리스크 지표
- `mdd_pct`: 최대 낙폭 (%)
- `mdd_duration_days`: MDD 지속 일수
- `daily_volatility`: 일일 변동성

#### 효율 지표
- `sharpe`: Sharpe Ratio (무위험 이자율 5% 연율 기준)
- `sortino`: Sortino Ratio (하방 변동성 기준)
- `calmar`: Calmar Ratio (연율화 수익 / MDD)

#### 거래 지표
- `total_trades`: 총 거래 횟수
- `win_rate`: 승률 (%)
- `profit_factor`: 수익 팩터 (총 이익 / 총 손실)
- `avg_win`: 평균 수익
- `avg_loss`: 평균 손실
- `avg_holding_days`: 평균 보유 일수
- `max_consecutive_losses`: 최대 연속 손실 횟수

#### 청산 분포
- `exit_distribution`: 청산 사유별 거래 건수
  - `atr_hard_stop`: ATR 기반 하드 스톱
  - `trailing_stop`: 추적 손절
  - `time_limit`: 시간 제한
  - `partial_take_profit`: 부분 익절
  - `stop_loss`: 고정 손절
  - `take_profit`: 고정 익절
  - `signal_sell`: 시그널 기반 매도
  - `other`: 기타

#### 벤치마크 비교
- `spy_return_pct`: SPY 동기간 수익률 (yfinance 조회)
- `alpha`: 전략 알파 (전략 수익 - SPY 수익)

#### 자동 진단
severity 순으로 정렬된 진단 결과:

| Severity | 조건 | 메시지 |
|----------|------|--------|
| CRITICAL | 동적 청산 비율 < 5% | "고정 SL/TP 종속" |
| CRITICAL | Alpha < -10% | "심각한 벤치마크 언더퍼폼" |
| HIGH | 월 평균 거래 < 5건 | "저빈도" |
| HIGH | Sharpe < 0.5 | "낮은 위험조정 수익" |
| MEDIUM | 평균 보유 일수 > 25일 | "과도 보유" |

### 2. 백테스트 비교 (`compare_reports`)

여러 백테스트의 주요 지표를 나란히 비교할 수 있습니다.

## API 사용법

### 리포트 생성

```http
GET /api/backtest/results/{backtest_id}/report
```

**응답 예시:**
```json
{
  "backtest_id": "bt-123",
  "metrics": {
    "profit": {
      "total_return_pct": 12.0,
      "annualized_return_pct": 15.5
    },
    "risk": {
      "mdd_pct": 8.5,
      "mdd_duration_days": 15,
      "daily_volatility": 0.0125
    },
    "efficiency": {
      "sharpe": 1.25,
      "sortino": 1.80,
      "calmar": 1.82
    },
    "trading": {
      "total_trades": 45,
      "win_rate": 62.5,
      "profit_factor": 2.1,
      "avg_win": 850.0,
      "avg_loss": -320.0,
      "avg_holding_days": 8.5,
      "max_consecutive_losses": 3
    },
    "exit_distribution": {
      "trailing_stop": 15,
      "atr_hard_stop": 10,
      "take_profit": 12,
      "stop_loss": 8
    }
  },
  "benchmark": {
    "spy_return_pct": 10.5,
    "alpha": 1.5
  },
  "diagnoses": [
    {
      "severity": "HIGH",
      "message": "낮은 위험조정 수익",
      "detail": "Sharpe 1.25 < 2.0 (권장)"
    }
  ]
}
```

### 백테스트 비교

```http
POST /api/backtest/compare
Content-Type: application/json

{
  "ids": ["bt-123", "bt-456"]
}
```

**응답 예시:**
```json
{
  "comparison": [
    {
      "backtest_id": "bt-123",
      "total_return_pct": 12.0,
      "annualized_return_pct": 15.5,
      "sharpe": 1.25,
      "sortino": 1.80,
      "calmar": 1.82,
      "mdd_pct": 8.5,
      "win_rate": 62.5,
      "total_trades": 45,
      "profit_factor": 2.1,
      "avg_holding_days": 8.5,
      "spy_alpha": 1.5,
      "exit_distribution": {
        "trailing_stop": 15,
        "atr_hard_stop": 10
      }
    },
    {
      "backtest_id": "bt-456",
      "total_return_pct": 15.0,
      "annualized_return_pct": 18.2,
      "sharpe": 1.45,
      "sortino": 2.10,
      "calmar": 2.05,
      "mdd_pct": 7.3,
      "win_rate": 65.0,
      "total_trades": 52,
      "profit_factor": 2.5,
      "avg_holding_days": 7.2,
      "spy_alpha": 4.5,
      "exit_distribution": {
        "trailing_stop": 20,
        "atr_hard_stop": 15
      }
    }
  ]
}
```

## Python 사용 예시

```python
from api.services.backtest_reporter import generate_report, compare_reports

# 단일 백테스트 리포트 생성
report = await generate_report("bt-123")

print(f"총 수익률: {report['metrics']['profit']['total_return_pct']}%")
print(f"Sharpe: {report['metrics']['efficiency']['sharpe']}")
print(f"승률: {report['metrics']['trading']['win_rate']}%")
print(f"Alpha: {report['benchmark']['alpha']}%")

# 진단 결과 확인
for diag in report['diagnoses']:
    print(f"[{diag['severity']}] {diag['message']}: {diag['detail']}")

# 여러 백테스트 비교
comparison = await compare_reports(["bt-123", "bt-456", "bt-789"])

for bt_report in comparison['comparison']:
    print(f"백테스트 {bt_report['backtest_id']}:")
    print(f"  수익률: {bt_report['total_return_pct']}%")
    print(f"  Sharpe: {bt_report['sharpe']}")
    print(f"  승률: {bt_report['win_rate']}%")
```

## 활용 사례

### 1. 전략 개선 방향 파악
```python
# 4-1 (ATR 사이징) 적용 전후 비교
comparison = await compare_reports(["before-atr", "after-atr"])

for report in comparison['comparison']:
    print(f"{report['backtest_id']}:")
    print(f"  승률: {report['win_rate']}%")
    print(f"  Profit Factor: {report['profit_factor']}")
    print(f"  평균 보유: {report['avg_holding_days']}일")
```

### 2. 동적 청산 효과 확인
```python
report = await generate_report("dynamic-exit-bt")

exit_dist = report['metrics']['exit_distribution']
total = sum(exit_dist.values())

dynamic_exits = exit_dist.get('atr_hard_stop', 0) + \
                exit_dist.get('trailing_stop', 0) + \
                exit_dist.get('time_limit', 0) + \
                exit_dist.get('partial_take_profit', 0)

dynamic_ratio = (dynamic_exits / total * 100) if total > 0 else 0
print(f"동적 청산 비율: {dynamic_ratio:.1f}%")
```

### 3. 벤치마크 대비 성과 분석
```python
report = await generate_report("my-strategy")

strategy_return = report['metrics']['profit']['annualized_return_pct']
spy_return = report['benchmark']['spy_return_pct']
alpha = report['benchmark']['alpha']

print(f"전략 연율화 수익: {strategy_return:.2f}%")
print(f"SPY 수익: {spy_return:.2f}%")
print(f"Alpha: {alpha:.2f}%")

if alpha > 5:
    print("✓ 벤치마크 대비 우수한 성과!")
elif alpha < -5:
    print("✗ 벤치마크 대비 부진한 성과")
```

## 주의사항

1. **exit_reason 추정**: trades에 exit_reason이 없는 경우, return_pct로 추정
   - return_pct ≈ -8.0 → `fixed_sl`
   - return_pct ≈ 15.0 → `fixed_tp`
   - 기타 → `other`

2. **yfinance 호출**: SPY 데이터 조회는 asyncio.to_thread로 별도 스레드에서 실행

3. **연율화 계산**: 252 거래일 기준으로 연율화 수익률 계산

4. **무위험 이자율**: Sharpe/Sortino 계산 시 5% 연율 사용

## 테스트

전체 테스트 실행:
```bash
python -m pytest tests/test_backtest_reporter.py -v
python -m pytest tests/test_backtest_reporter_api.py -v
python -m pytest tests/test_backtest_integration_reporter.py -v
python -m pytest tests/test_completion_criteria.py -v
```

특정 완료 기준 검증:
```bash
python -m pytest tests/test_completion_criteria.py -v -s
```

## 파일 구조

```
api/
├── services/
│   └── backtest_reporter.py       # 리포트 생성 로직
└── routers/
    └── backtest.py                 # API 엔드포인트

tests/
├── test_backtest_reporter.py              # 핵심 기능 테스트 (10개)
├── test_backtest_reporter_api.py          # API 엔드포인트 테스트 (4개)
├── test_backtest_integration_reporter.py  # 통합 테스트 (2개)
└── test_completion_criteria.py            # 완료 기준 검증 (4개)
```

## 향후 개선 가능 사항

1. 리포트 결과 DB 영구 저장
2. 월별/분기별 성과 분해 (breakdown)
3. 섹터별 성과 분석
4. 시계열 차트 생성 (daily_equity 시각화)
5. 상관관계 분석 (여러 전략 간)
6. 리스크 조정 수익 순위 (여러 백테스트 간)
