### 프롬프트 사용 가이드

이상의 15개 프롬프트는 다음 순서로 실행하되, Phase 간 의존성을 준수해야 한다.

**준비 사항 (Prerequisites):**

- 모든 라이브러리 설치: `pip install -r requirements.txt` (ModuleNotFoundError 발생 시 필수 실행)
- DB 초기화: `python scripts/init_db.py`

**즉시 실행 가능 (병렬):** 1-1, 1-2, 1-4, 1-5는 서로 독립적이므로 동시에 진행할 수 있다.

**순서 의존:**

- 1-3(stop-loss)은 1-6(async 전환)과 함께 진행하는 것이 효율적이다.
- 2-2(백테스트 엔진)는 2-1(히스토리컬 데이터)이 선행되어야 한다.
- 2-4(감도 분석)는 2-2 + 2-3이 완료된 후 진행한다.
- **[중간 점검 1] Phase 3 진입 전:** 4-2(동적 청산)를 적용한 백테스트를 수행하여 Baseline 성과(수익률, MDD, 평균 보유일)를 기록한다.
- 3-1, 3-2, 3-3은 서로 독립적이지만 모두 Phase 2의 백테스트로 효과를 검증해야 한다.
- **[중간 점검 2] Phase 3 완료 후:** 추가된 모델(FinBERT, LSTM)로 인해 Ollama와 시스템 메모리(RAM) 간의 경합이 발생하는지 `api/ollama/status`를 통해 확인한다.
- Phase 4는 Phase 2 완료 후 진행한다.
- Phase 5는 Phase 1~4 전체 완료 후 진행한다.
- **[중간 점검 3] 5-2(Live Gate) 전:** 최소 3거래일 이상의 Paper Trading(Alpaca)을 통해 주문 체결 및 로그 기록의 정합성을 최종 확인한다.

---

### 테스트 및 검증 명령어

각 프롬프트 작업 완료 후 다음 단계에 따라 검증을 수행한다.

#### 1. 단위 및 통합 테스트 (pytest)

기존 로직이 깨지지 않았는지 확인한다.

```bash
# 전체 테스트 실행
pytest tests/ -v

# 특정 모듈 관련 테스트만 실행 (예: 청산 로직 수정 시)
pytest tests/test_exit_logic.py -v
pytest tests/test_backtest_reporter.py -v
```

#### 2. 전략 성과 검증 (Backtest)

새로운 알고리즘(알파) 추가 시 수익성과 리스크 지표를 확인한다.

```bash
# 백테스트 실행 (API 호출 예시 - start/end date 조정 필요)
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 100000,
    "exit_strategy": "dynamic"
  }'
```

*결과 확인 포인트:* `Sharpe Ratio` 증가 여부, `Max Drawdown (MDD)` 감소 여부, `Win Rate` 변화.

#### 3. 시스템 상태 점검 (Health Check)

로컬 LLM 및 리소스 상태를 확인한다.

```bash
# Ollama 모델 로드 상태 및 응답 확인
curl http://localhost:8000/api/ollama/status

# 시스템 전체 헬스체크
curl http://localhost:8000/api/health
```

---

### 핵심 원칙

1. 각 프롬프트의 출력물을 반영한 후 반드시 기존 테스트가 깨지지 않는지 확인한다.
2. 해당 모듈의 변경이 다른 모듈에 미치는 영향을 추적한다.
3. **성과 측정:** Phase 2의 백테스트로 전략 성과 변화를 측정한다. (수익률 저하 또는 MDD 증가 시 즉시 롤백 및 원인 분석)
4. **리소스 모니터링:** 로컬 LLM 환경이므로 새로운 분석 축 추가 시 추론 속도 저하를 반드시 체크한다.


1. 2-4: `backtest_optimizer.py` - Sensitivity/grid search
2. 3-1: FinBERT sentiment
3. 3-2: LSTM predictor
4. 3-3: RAG hybrid search
5. 5-1: Monitoring/alerting
6. 5-2: Live gate
