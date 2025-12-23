# Copilot / AI Agent Quick Guide — YangtzeDestoryLLM

> Concise, actionable instructions for AI coding agents working with this Yangtze disaster knowledge graph RAG system.

## Architecture Overview 🔧

**CQ-Driven Pipeline (P1→P5):** Core workflow that generates knowledge graphs from text:
- **P1**: Domain description → Competency Questions (CQs) via LLM
- **P2**: CQs → Initial TBox (class/relation/attribute definitions)
- **P3**: TBox normalization (naming, deduplication, conflict detection)
- **P4**: TBox enhancement from sample corpus
- **P5**: Event & triple extraction (ABox) constrained by TBox

**Data Flow:** Raw corpus → `tools/corpus_cleaner.py` → `tools/filter_corpus_light.py` → P1-P5 pipeline → NetworkX graph or Neo4j

**Key Components:**
- `kg/llm_core.py` — Multi-provider LLM wrapper (OpenAI, ZhipuAI, Gemini) with key rotation and rate-limit handling
- `kg/cq_pipeline.py` — `CQLLMPipeline` class orchestrating P1-P5 with `TBoxSchema`, `ClassDef`, `RelationDef` dataclasses
- `kg/query.py` — `GraphRAG` class combining BM25/vector retrieval with multi-hop graph expansion
- `retrievers/graph_retriever.py` — Semantic, BM25, and multi-hop retrieval strategies

## File & Directory Map 📁

| Path | Purpose |
|------|---------|
| `configs/cfg.yaml` | Central config: paths, LLM settings, P1-P5 parameters, filtering thresholds |
| `scripts/run_cq_pipeline.py` | Main pipeline entrypoint (P1-P5, supports `--start-step`, `--p4-file`, etc.) |
| `scripts/run_full_pipeline.sh` | End-to-end shell orchestrator with `--dry-run` support |
| `kg/prompts.py` | All prompt templates for P1-P5 stages |
| `kg/utils/` | Deduplication, entity linking, conflict detection, schema alignment |
| `tools/` | Corpus cleaning, filtering, manifest building, eval pool generation |
| `outputs/cq_pipeline/final/` | Default output: `p1_cqs.json`, `p2_tbox_init.json`, `p5_events.json` |

## Developer Workflows ⚙️

```bash
# Environment setup
conda create -n YangtzeLLM python=3.10 && conda activate YangtzeLLM
pip install -r requirements.txt

# API keys (use .env or export)
export OPENAI_API_KEYS="key1,key2,key3"  # Multi-key rotation supported
export ZHIPU_API_KEY="xxx"               # For ZhipuAI provider

# Run full pipeline (dry-run first)
./scripts/run_full_pipeline.sh --dry-run
./scripts/run_full_pipeline.sh --start-step p3  # Resume from P3

# Run specific stages
python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash --n-cq 20
python scripts/run_cq_pipeline.py --start-step p5 --p4-file outputs/p4_tbox.json

# Tests
pytest -q tests/
```

## Project-Specific Patterns ✅

**Config Priority:** CLI args > `cfg.yaml` > hardcoded defaults. Pattern used throughout:
```python
def pick(*vals, default=None):
    for v in vals:
        if v not in (None, ""):
            return v
    return default
# Usage: provider = pick(args.provider, cfg["llm"]["provider"], "openai")
```

**LLM JSON Parsing:** `kg/cq_pipeline.py:LLMJsonClient` handles markdown fence stripping, JSON substring extraction, and array-to-dict wrapping automatically.

**HuggingFace Mirror:** `retrievers/vector_retriever.py` sets `HF_ENDPOINT=https://hf-mirror.com` for faster model downloads in China.

**Neo4j Optional:** `kg/neo4j_adapter.py` gracefully degrades when `neo4j` package not installed.

## Integration Points & Pitfalls 🔗

- **LLM Rate Limits:** `kg/llm_core.py` implements key rotation (`OPENAI_API_KEYS` comma-separated) and cooldown tracking
- **Per-Stage LLM Config:** `cfg.yaml` supports `llm_per_stage.p1/.p2/...` for different models per pipeline stage
- **Long-Running Batches:** P4/P5 batch scripts write intermediate files to `outputs/cq_pipeline/process/` — use `--output-dir` for isolation
- **Data Paths are Symlinks:** `data/` and `outputs/` may be symlinks to external storage (see `STORAGE_CONFIG.md`)

## Logging

Initialize via `tools/logging_utils.init_logging(cfg["logging"])`. Config in `cfg.yaml`:
```yaml
logging:
  level: info
  file: ""  # Empty = stdout only
```

## When to Ask Human ❗

- Missing API keys for LLM providers (check `.env` or ask for test keys)
- Large model downloads failing (configure `models_cache` path in `cfg.yaml`)
- Neo4j connection issues (need `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`)
- Unclear which TBox JSON to use as input for P5 extraction