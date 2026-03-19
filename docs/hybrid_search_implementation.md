# Hybrid Search Integration - Implementation Summary

## Overview
This implementation integrates ChromaDB hybrid search combining BGE-M3 (Ollama) and Gemini embeddings using Reciprocal Rank Fusion (RRF) for the AlphaFlow US trading system.

## Changes Made

### 1. New File: `api/services/hybrid_search.py`
- **Function**: `hybrid_search(query, symbol=None, top_k=5)`
  - Combines results from both `stock_news` (BGE-M3) and `stock_news_gemini` collections
  - Uses Reciprocal Rank Fusion (RRF) algorithm: `score(doc) = Σ 1/(60 + rank_i)`
  - Returns top_k results sorted by rrf_score descending
  - Each result includes: `{id, text, metadata, rrf_score, source}`

- **Graceful Fallback**:
  - If one collection is empty or embedding fails, automatically uses the other
  - If both fail, returns empty list (no crash)

### 2. Modified: `api/services/rag_engine.py`
- Added `_get_rag_search_method()` function to read from settings table
- Modified `search_and_build_prompt()` to branch based on search method:
  - `"bge"` → Uses `search_similar_news()` (Ollama/BGE-M3)
  - `"gemini"` → Uses `search_gemini_news()` (Gemini embeddings)
  - `"hybrid"` → Uses `hybrid_search()` (RRF combination)
- Default: `"bge"` if setting not found or invalid

### 3. Database Migration: `scripts/migrate_002_rag_search_method.sql`
- Adds new setting: `rag_search_method` with default value `"bge"`
- Valid values: `"bge"`, `"gemini"`, `"hybrid"`

### 4. Comprehensive Tests
- **`tests/test_hybrid_search.py`** (15 tests)
  - Tests RRF algorithm correctness
  - Tests graceful fallback scenarios
  - Tests error handling for both collections

- **`tests/test_rag_engine_search_methods.py`** (13 tests)
  - Tests search method branching logic
  - Tests settings table integration
  - Tests parameter passing to search functions

**Total: 28 new tests, all passing**

## How to Use

### Step 1: Run Database Migration
```sql
-- Run the migration to add the rag_search_method setting
\i scripts/migrate_002_rag_search_method.sql
```

### Step 2: Configure Search Method
```sql
-- Option A: Use BGE-M3 only (default)
UPDATE settings SET value = 'bge' WHERE key = 'rag_search_method';

-- Option B: Use Gemini only
UPDATE settings SET value = 'gemini' WHERE key = 'rag_search_method';

-- Option C: Use Hybrid (RRF combination)
UPDATE settings SET value = 'hybrid' WHERE key = 'rag_search_method';
```

### Step 3: Use RAG Analysis as Normal
```python
from api.services.rag_analyzer import analyze_stock

# The search method is automatically selected based on settings
result = await analyze_stock("AAPL")
```

## Reciprocal Rank Fusion Algorithm

RRF is a simple yet effective algorithm for combining ranked lists from multiple sources:

```
For each document d appearing in source i at rank r_i:
    rrf_score(d) = Σ 1/(k + r_i)

Where k = 60 (standard constant)
```

**Benefits:**
- Documents appearing in multiple sources get higher scores
- Rank position matters more than absolute similarity scores
- Robust to scale differences between embedding models

## Expected Behavior

### With Both Collections Populated (Hybrid Mode)
- Fetches top_k × 2 from each collection
- Applies RRF to combine and re-rank
- Returns top_k final results
- Documents in both collections rank higher (better recall)

### With One Collection Empty
- Automatically falls back to the available collection
- No errors or crashes
- Logs warning about which collection is empty

### With Text Weight = 0
- Hybrid search still works (fetches and combines results)
- **However**: RAG analysis impact on trading signals is minimal until text weight > 0
- This is expected behavior per the problem statement

## Testing

Run the test suite:
```bash
# Run all hybrid search tests
python -m pytest tests/test_hybrid_search.py -v

# Run all RAG engine tests
python -m pytest tests/test_rag_engine_search_methods.py -v

# Run all RAG-related tests
python -m pytest tests/test_hybrid_search.py tests/test_rag_engine_search_methods.py tests/test_rag_analyzer.py -v
```

## Completion Criteria

✅ **All criteria met:**
1. ✅ Settings table has `rag_search_method` with default "bge"
2. ✅ RAG engine branches to bge/gemini/hybrid based on setting
3. ✅ Hybrid search uses RRF with k=60
4. ✅ Each result includes {id, text, metadata, rrf_score, source}
5. ✅ Graceful fallback when one collection is empty
6. ✅ No errors when executing RAG analysis with rag_search_method="hybrid"
7. ✅ Comprehensive test coverage (28 tests, all passing)

## Future Enhancements

- **Weighted RRF**: Allow different weights for BGE vs Gemini sources
- **Adaptive top_k**: Dynamically adjust fetch size based on collection sizes
- **Diversity Filtering**: Ensure results include diverse time periods or sentiment labels
- **Performance Monitoring**: Log search latency and success rates per method
