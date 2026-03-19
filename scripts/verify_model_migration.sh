#!/bin/bash
# scripts/verify_model_migration.sh

echo "========================================="
echo "AlphaFlow US 모델 마이그레이션 검증"
echo "========================================="

# ── 설정 ──
GEMINI_API_KEY="${GEMINI_API_KEY:-$(grep GEMINI_API_KEY .env 2>/dev/null | cut -d'=' -f2)}"

# ── 1. Ollama 서버 상태 ──
echo ""
echo "[1/7] Ollama 서버 상태 확인..."
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
print(f'  로드된 모델: {models}')

# bge-m3:latest 도 bge-m3 로 인식
normalized = set()
for m in models:
    normalized.add(m)
    normalized.add(m.split(':')[0])  # 태그 제거한 이름도 추가

required = {'qwen3.5:4b', 'bge-m3'}
missing = set()
for r in required:
    if r not in normalized and r.split(':')[0] not in normalized:
        missing.add(r)

if missing:
    print(f'  ❌ 누락 모델: {missing}')
else:
    print('  ✅ 필수 모델 모두 존재')

# 삭제 대상 확인
old_models = {'qwen3:4b', 'qwen3:8b', 'qwen3-vl:8b', 'gemma3:4b'}
remaining = old_models & normalized
if remaining:
    print(f'  ⚠️  미삭제 구 모델: {remaining}')
else:
    print('  ✅ 구 모델 모두 삭제됨')
"

# ── 2. 텍스트 생성 테스트 (thinking 모드 대응) ──
echo ""
echo "[2/7] 감정 분석 (qwen3.5:4b) 테스트..."
RESPONSE=$(curl -s http://localhost:11434/api/generate \
  -d '{
    "model": "qwen3.5:4b",
    "prompt": "Analyze sentiment: Apple beats earnings expectations. Respond JSON only: {\"sentiment_score\": 0.8, \"label\": \"positive\"}",
    "stream": false,
    "options": {
      "temperature": 0.1,
      "num_predict": 512
    }
  }')
echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
resp = data.get('response', '')

# thinking 태그 제거 후 실제 응답 추출
import re
# <think>...</think> 블록 제거
cleaned = re.sub(r'<think>.*?</think>', '', resp, flags=re.DOTALL).strip()

print(f'  전체 응답 길이: {len(resp)} chars')
print(f'  thinking 제거 후: {len(cleaned)} chars')

if '{' in cleaned and '}' in cleaned:
    print('  ✅ JSON 형식 응답 확인')
    # JSON 추출 시도
    match = re.search(r'\{[^}]+\}', cleaned)
    if match:
        try:
            parsed = json.loads(match.group())
            print(f'  ✅ JSON 파싱 성공: {parsed}')
        except:
            print(f'  ⚠️  JSON 파싱 실패, 원문: {match.group()[:100]}')
elif len(resp) > 0 and '<think>' in resp:
    print('  ⚠️  thinking 출력만 있고 실제 응답 없음 (num_predict 부족 가능)')
    print(f'  응답 끝부분: ...{resp[-150:]}')
else:
    print('  ❌ 응답 없음')
    print(f'  raw: {resp[:200]}')
"

# ── 3. Thinking 비활성화 테스트 ──
echo ""
echo "[3/7] Thinking OFF 모드 테스트..."
RESPONSE2=$(curl -s http://localhost:11434/api/chat \
  -d '{
    "model": "qwen3.5:4b",
    "messages": [
      {
        "role": "user",
        "content": "Return only JSON: {\"test\": true}"
      }
    ],
    "stream": false,
    "options": {
      "temperature": 0.1,
      "num_predict": 128
    },
    "think": false
  }')
echo "$RESPONSE2" | python3 -c "
import sys, json
data = json.load(sys.stdin)
msg = data.get('message', {})
content = msg.get('content', '')
thinking = msg.get('thinking', '')

print(f'  thinking 길이: {len(thinking)} chars')
print(f'  content 길이: {len(content)} chars')

if content and '{' in content:
    print('  ✅ think=false 모드 정상 작동')
    print(f'  응답: {content[:150]}')
else:
    print('  ⚠️  think=false 모드 응답 확인 필요')
    print(f'  content: {content[:150]}')
    if thinking:
        print(f'  thinking: {thinking[:100]}...')
"

# ── 4. Gemini 비전 API 테스트 ──
echo ""
echo "[4/7] Gemini 비전 API 테스트..."
if [ -z "$GEMINI_API_KEY" ]; then
    echo "  ⚠️  GEMINI_API_KEY 미설정, 스킵"
else
    # 1x1 빨간 PNG base64
    IMG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

    GEMINI_RESP=$(curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}" \
      -H 'Content-Type: application/json' \
      -X POST \
      -d '{
        "contents": [{
          "parts": [
            {
              "inline_data": {
                "mime_type": "image/png",
                "data": "'"$IMG_B64"'"
              }
            },
            {"text": "What color is this image? Respond in one word."}
          ]
        }],
        "generationConfig": {
          "temperature": 0.1,
          "maxOutputTokens": 64
        }
      }')

    echo "$GEMINI_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
candidates = data.get('candidates', [])
if candidates:
    parts = candidates[0].get('content', {}).get('parts', [])
    text = ''.join(p.get('text', '') for p in parts)
    print(f'  ✅ Gemini 비전 응답: {text.strip()[:100]}')
else:
    error = data.get('error', {})
    if error:
        print(f'  ❌ Gemini 오류: {error.get(\"message\", \"unknown\")}')
    else:
        print(f'  ❌ Gemini 응답 없음: {json.dumps(data)[:200]}')
"
fi

# ── 5. 임베딩 테스트 (bge-m3) ──
echo ""
echo "[5/7] 임베딩 모델 (bge-m3) 테스트..."
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

# ── 6. FastAPI 서버 헬스체크 ──
echo ""
echo "[6/7] FastAPI 서버 확인..."
# 여러 가능한 엔드포인트 시도
for endpoint in "/api/system/health" "/health" "/api/health" "/docs"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000${endpoint}" 2>/dev/null)
    if [ "$CODE" = "200" ]; then
        echo "  ✅ ${endpoint} → HTTP ${CODE}"
        break
    fi
done
if [ "$CODE" != "200" ]; then
    echo "  ⚠️  서버 미실행 또는 엔드포인트 확인 필요 (마지막 응답: HTTP ${CODE})"
fi

# ── 7. 최종 모델 디스크 사용량 ──
echo ""
echo "[7/7] 모델 디스크 사용량..."
ollama list 2>/dev/null | while read line; do
    echo "  $line"
done

# ── 요약 ──
echo ""
echo "========================================="
echo "검증 요약"
echo "========================================="
echo "  로컬 LLM:    qwen3.5:4b (감정분석 + RAG)"
echo "  임베딩:      bge-m3 (로컬) + Gemini Embedding (클라우드)"
echo "  비전 분석:   Gemini 2.5 Flash API (클라우드)"
echo "  텍스트 생성: Gemini 2.5 Flash API (폴백)"
echo "========================================="
echo ""
