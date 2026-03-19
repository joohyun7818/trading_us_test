#!/bin/bash
# scripts/verify_model_migration.sh

echo "========================================="
echo "AlphaFlow US 모델 마이그레이션 검증"
echo "========================================="

# 1. Ollama 서버 상태
echo ""
echo "[1/6] Ollama 서버 상태 확인..."
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
print(f'  로드된 모델: {models}')
required = {'qwen3.5:4b', 'bge-m3'}
missing = required - set(models)
if missing:
    print(f'  ❌ 누락 모델: {missing}')
    sys.exit(1)
else:
    print('  ✅ 필수 모델 모두 존재')

# 삭제 대상이 남아있는지 확인
old_models = {'qwen3:4b', 'qwen3:8b', 'qwen3-vl:8b'}
remaining = old_models & set(models)
if remaining:
    print(f'  ⚠️  미삭제 구 모델: {remaining}')
else:
    print('  ✅ 구 모델 모두 삭제됨')
"

# 2. 텍스트 생성 테스트 (감정 분석)
echo ""
echo "[2/6] 감정 분석 (FAST_MODEL) 테스트..."
RESPONSE=$(curl -s http://localhost:11434/api/generate \
  -d '{
    "model": "qwen3.5:4b",
    "prompt": "Analyze sentiment: Apple beats earnings expectations. Respond JSON only: {\"sentiment_score\": 0.0, \"label\": \"neutral\"} /no_think",
    "stream": false,
    "options": {"temperature": 0.1, "num_predict": 256}
  }')
echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
resp = data.get('response', '')
print(f'  응답 길이: {len(resp)} chars')
if '{' in resp and '}' in resp:
    print('  ✅ JSON 형식 응답 확인')
else:
    print('  ⚠️  JSON 형식이 아닐 수 있음')
print(f'  응답 미리보기: {resp[:200]}')
"

# 3. 이미지 입력 테스트 (비전)
echo ""
echo "[3/6] 비전 모델 (멀티모달) 테스트..."
# 1x1 빨간 PNG를 base64로 생성
IMG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
VISION_RESP=$(curl -s http://localhost:11434/api/generate \
  -d "{
    \"model\": \"qwen3.5:4b\",
    \"prompt\": \"What do you see in this image? Respond briefly. /no_think\",
    \"images\": [\"$IMG_B64\"],
    \"stream\": false,
    \"options\": {\"temperature\": 0.1, \"num_predict\": 128}
  }")
echo "$VISION_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
resp = data.get('response', '')
if resp:
    print('  ✅ 멀티모달 응답 성공')
    print(f'  응답: {resp[:150]}')
else:
    err = data.get('error', 'unknown')
    print(f'  ❌ 멀티모달 실패: {err}')
"

# 4. 임베딩 테스트 (bge-m3)
echo ""
echo "[4/6] 임베딩 모델 (bge-m3) 테스트..."
EMBED_RESP=$(curl -s http://localhost:11434/api/embed \
  -d '{
    "model": "bge-m3",
    "input": "Apple stock price analysis"
  }')
echo "$EMBED_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
embeddings = data.get('embeddings', [[]])
dim = len(embeddings[0]) if embeddings and embeddings[0] else 0
if dim > 0:
    print(f'  ✅ 임베딩 성공: {dim}차원')
else:
    print('  ❌ 임베딩 실패')
"

# 5. FastAPI 서버 헬스체크
echo ""
echo "[5/6] FastAPI 서버 확인..."
API_RESP=$(curl -s http://localhost:8000/api/system/health 2>/dev/null || echo '{"error":"not running"}')
echo "  응답: $API_RESP"

# 6. 디스크 사용량
echo ""
echo "[6/6] 모델 디스크 사용량..."
ollama list 2>/dev/null | while read line; do
    echo "  $line"
done

echo ""
echo "========================================="
echo "검증 완료"
echo "========================================="
