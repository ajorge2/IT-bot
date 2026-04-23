# IT Knowledge Base Chatbot — Project Summary

---

## What This Is

A private-cloud RAG chatbot for internal IT self-service at a financial firm. Employees ask IT questions in plain English; the bot retrieves relevant knowledge base content and answers with mandatory inline citations. Low-confidence answers automatically append a disclaimer and generate a support ticket draft for the user to review and submit.

**Hard constraints:** All data stays inside the private cloud. Every response cites its source. No LangChain for retrieval, prompt construction, or LLM calls — those are owned, auditable code.

---

## Project Structure

```
IT-bot/
├── app/
│   ├── config.py               ← All settings and constants (env vars via pydantic-settings)
│   ├── audit.py                ← Structured JSON audit logging (compliance)
│   ├── ingestion/
│   │   ├── loaders.py          ← Confluence and SharePoint loaders
│   │   ├── sample_loader.py    ← Sample data loader (used when USE_SAMPLE_DATA=true)
│   │   ├── chunker.py          ← 512-token chunks, 50-token overlap
│   │   └── indexer.py          ← Orchestrates full ingestion pipeline + builds BM25 index
│   ├── vectorstore/
│   │   └── faiss_store.py      ← FAISS HNSW index + SQLite for metadata
│   ├── retrieval/
│   │   ├── dense.py            ← FAISS cosine similarity search via Voyage AI embeddings
│   │   ├── sparse.py           ← BM25 loaded from disk (rank_bm25)
│   │   ├── fusion.py           ← Reciprocal rank fusion
│   │   ├── reranker.py         ← ms-marco-MiniLM-L-6-v2 cross-encoder
│   │   └── pipeline.py         ← Entry point: runs all 4 steps
│   ├── generation/
│   │   ├── prompt.py           ← Builds messages list for LLM
│   │   ├── llm.py              ← Calls Anthropic Claude with system prompt caching
│   │   ├── response.py         ← Parses citations, computes confidence, builds output
│   │   └── handler.py          ← Post-LLM confidence gate + ticket draft generation
│   └── evaluation/
│       └── ragas_eval.py       ← RAGAS metrics runner
├── api/
│   └── main.py                 ← FastAPI backend
├── frontend/
│   └── index.html              ← Plain HTML/CSS/JS chat UI (served by FastAPI at /ui)
├── data/
│   ├── faiss.index             ← FAISS HNSW vector index
│   ├── chunks.db               ← SQLite metadata store
│   ├── bm25.pkl                ← Pickled BM25 index (built at ingestion time)
│   └── sample/                 ← Sample Confluence + SharePoint fixtures
├── requirements.txt
└── .env.example                ← Template for all secrets/config
```

---

## How the Pipeline Works

### Ingestion (manual `/ingest` or script)

```
Confluence (LangChain loader)  ─┐
SharePoint (LangChain loader)  ─┴─→ [Chunker] 512-token chunks, 50-token overlap
                                          ↓
                                  [Voyage AI] voyage-finance-2 embeddings
                                          ↓
                              [FAISSStore] vectors → faiss.index (HNSW)
                                          metadata → chunks.db (SQLite)
                                          ↓
                              [BM25 index] built from corpus, pickled → bm25.pkl
```

### Query (per user request)

```
User query
    │
    ├──→ [Dense retrieval]   Voyage AI query embedding → FAISS cosine similarity → top-20
    └──→ [Sparse retrieval]  BM25 loaded from bm25.pkl → top-20
              │
              ▼
    [RRF fusion]  1/(k+rank) per list, summed per doc → single ranked list
              │
              ▼
    [Cross-encoder reranker]  ms-marco-MiniLM-L-6-v2 → top-5 chunks
              │
              ▼
    [LLM call]  claude-opus-4-7, temperature=0.0, system prompt caching
              │
              ▼
    [Citation parsing]  Regex extracts every [N] reference from LLM answer
              │
              ▼
    [Post-LLM confidence]  Avg cosine similarity of cited chunks
              ├── score ≥ 0.6 → answer normally, cite only used sources
              └── score < 0.6 → append disclaimer + auto-draft ticket for user review
```

---

## Key Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `VOYAGE_API_KEY` | Voyage AI API key |
| `VOYAGE_MODEL` | Embedding model (default: `voyage-finance-2`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | Claude model to use (default: `claude-opus-4-7`) |
| `FAISS_INDEX_PATH` | Path to the FAISS index file |
| `FAISS_DB_PATH` | Path to the SQLite metadata database |
| `BM25_INDEX_PATH` | Path to the pickled BM25 index |
| `CHUNK_TOKENS` | Chunk size in tokens (default: `512`) |
| `CHUNK_OVERLAP_TOKENS` | Overlap between chunks in tokens (default: `50`) |
| `RRF_K` | RRF constant (default: `60`) |
| `RETRIEVAL_TOP_K` | Candidates fetched by dense + sparse search (default: `20`) |
| `RETRIEVAL_FINAL_TOP_N` | Chunks passed to LLM after reranking (default: `5`) |
| `CONFIDENCE_THRESHOLD` | Below this → disclaimer + ticket draft (default: `0.6`) |
| `RERANKER_MODEL` | Cross-encoder model name |
| `API_SECRET_KEY` | Guards the `/ingest` admin endpoint |
| `USE_SAMPLE_DATA` | Load sample fixtures instead of real connectors (default: `true`) |

---

## Getting Started

```bash
# 1. Configure environment
cp .env.example .env
# Fill in VOYAGE_API_KEY, ANTHROPIC_API_KEY, API_SECRET_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run ingestion (creates data/faiss.index, data/chunks.db, data/bm25.pkl)
curl -X POST http://localhost:8000/ingest -H "X-Admin-Secret: your-secret"

# 4. Start the API (UI served at http://localhost:8000/ui)
uvicorn api.main:app --reload

# 5. (Optional) Run RAGAS evaluation
python -m app.evaluation.ragas_eval --golden tests/golden_set.json
```

---

## Audit Logging

Every request writes two structured JSON entries (via structlog):

- **`chat.request`** — user ID, query length, client IP
- **`chat.response`** — user ID, `pre_llm_top_similarity` (best cosine similarity from dense retrieval), `post_llm_confidence_score` (avg cosine similarity of cited chunks), `low_confidence`, number of citations

The gap between `pre_llm_top_similarity` and `post_llm_confidence_score` is a useful diagnostic: if pre is high but post is low, the LLM leaned on sparse-retrieved chunks even though strong dense matches existed.

Enable `LOG_LEVEL=DEBUG` to get per-stage retrieval breakdowns (dense rank/similarity, BM25 rank/score, RRF scores, reranker scores) for every query.

---

## What Still Needs Doing Before Go-Live

- [ ] **Populate `tests/golden_set.json`** with ~50 real IT questions + known correct answers
- [ ] **Run golden set eval** — validate RRF equal weighting, `CONFIDENCE_THRESHOLD`, `RRF_K`, and `RETRIEVAL_TOP_K` against real queries
- [ ] **Connect real Confluence and SharePoint** — add credentials and set `USE_SAMPLE_DATA=false`
- [ ] **Decide document permissions** — chatbot currently serves all indexed content to all users. If role-based access is required, add a user-group filter to `faiss_store.similarity_search()`
- [ ] **Configure audit log shipping** — `app/audit.py` writes structured JSON; point it at your SIEM

---

## Architecture Decisions

| Decision | Rationale |
|---|---|
| FAISS + SQLite over pgvector/Qdrant/Pinecone | At 2k–5k vectors, a dedicated vector DB adds ops complexity with no perf benefit. FAISS with SQLite keeps everything on disk with no server process — no Docker, no Postgres, no infrastructure to manage. |
| Voyage AI (`voyage-finance-2`) for embeddings | Anthropic-recommended embedding provider; finance-domain model is well suited to a financial firm's IT content. API-based so no local GPU/RAM overhead. |
| BM25 built at ingestion, pickled to disk | Avoids rebuilding the index on every query. Loaded once into memory at first query via `lru_cache`. |
| Manual retrieval, prompt, and LLM code (no LangChain) | Compliance obligations live here — must be auditable code the firm owns. LangChain is used only for document loaders, the text splitter, and the `Document` type — no retrieval or generation logic. |
| BM25 + dense hybrid | Dense catches semantic matches; BM25 catches exact terms (error codes, product names). |
| RRF with equal weighting and k=60 | Standard defaults — equal weighting assumes neither method dominates; k=60 is the widely-used constant. Both should be validated on the golden set. |
| Cross-encoder reranker | Biggest single accuracy lever. Re-scores RRF candidates by reading query and document together, not just comparing vectors. |
| Post-LLM confidence gate | Confidence computed from avg cosine similarity of chunks the LLM actually cited. More honest than a pre-LLM proxy — only what went into the answer counts. |
| `temperature=0.0` | Deterministic outputs required for auditability. |
| No auto-ticket submission | User reviews the draft — bot never takes external action autonomously. |
| System prompt in `config.py` | Treated as a tunable constant alongside other settings. Caching applied via Anthropic's `ephemeral` cache control to reduce token costs on repeated requests. |
