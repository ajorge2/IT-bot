# IT Knowledge Base Chatbot — Project Summary

*Built 2026-04-12 from `plannerPKA/Andrew's Inbox/RAG-architecture-recommendation.md` (authored by Vera)*

---

## What This Is

A private-cloud RAG chatbot for internal IT self-service at a financial firm. Employees ask IT questions in plain English; the bot retrieves relevant knowledge base content and answers with mandatory citations. Low-confidence answers automatically generate a support ticket draft for the user to review and submit.

**Hard constraints:** All data stays inside the private cloud. Every response cites its source. No LangChain for retrieval, prompt construction, or LLM calls — those are owned, auditable code.

---

## Project Structure

```
IT-bot/
├── app/
│   ├── config.py               ← All settings (env vars via pydantic-settings)
│   ├── audit.py                ← Structured JSON audit logging (compliance)
│   ├── ingestion/
│   │   ├── loaders.py          ← Confluence, SharePoint, ticket loaders
│   │   ├── chunker.py          ← 512-token chunks, 50-token overlap
│   │   └── indexer.py          ← Orchestrates full ingestion pipeline
│   ├── embeddings/
│   │   └── embedder.py         ← Azure OpenAI / Bedrock / self-hosted BGE
│   ├── vectorstore/
│   │   └── pgvector_store.py   ← pgvector on PostgreSQL, HNSW index
│   ├── retrieval/
│   │   ├── dense.py            ← pgvector cosine similarity
│   │   ├── sparse.py           ← BM25 (rank_bm25)
│   │   ├── fusion.py           ← Reciprocal rank fusion
│   │   ├── reranker.py         ← ms-marco-MiniLM-L-6-v2 cross-encoder
│   │   └── pipeline.py         ← Entry point: runs all 4 steps
│   ├── generation/
│   │   ├── prompt.py           ← Builds messages list (hardcoded system prompt)
│   │   ├── llm.py              ← Calls private LLM endpoint
│   │   └── response.py         ← Injects citations, structures output
│   ├── confidence/
│   │   └── handler.py          ← Threshold gate + ticket draft generation
│   └── evaluation/
│       └── ragas_eval.py       ← RAGAS metrics runner
├── api/
│   └── main.py                 ← FastAPI backend
├── frontend/
│   └── app.py                  ← Streamlit UI
├── teams_bot/
│   └── bot.py                  ← Teams bot (thin wrapper over FastAPI)
├── scripts/
│   └── reindex.py              ← Nightly re-index script
├── tests/
│   └── golden_set.json         ← 50-question golden test set (populate with real Q&A)
├── docker-compose.yml          ← Postgres + API + frontend
├── Dockerfile
├── requirements.txt
└── .env.example                ← Template for all secrets/config
```

---

## How the Pipeline Works

```
User query
    │
    ▼
[Dense retrieval]  pgvector cosine similarity  → top-20 candidates
[Sparse retrieval] BM25 (rank_bm25)            → top-20 candidates
    │
    ▼
[RRF fusion]  Reciprocal rank fusion merges both lists
    │
    ▼
[Reranker]  ms-marco-MiniLM-L-6-v2 cross-encoder → top-5 chunks
    │
    ▼
[Confidence check]  top cosine similarity < 0.6?
    ├── YES → answer + disclaimer + auto-draft ticket
    └── NO  → answer normally
    │
    ▼
[LLM call]  Private endpoint, temperature=0.0, hardcoded system prompt
    │
    ▼
Response with mandatory citations
```

---

## Key Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `EMBEDDING_PROVIDER` | `azure_openai` / `bedrock` / `self_hosted` |
| `AZURE_OPENAI_*` | Embedding + LLM endpoint credentials |
| `LLM_BASE_URL / LLM_API_KEY / LLM_DEPLOYMENT` | Private LLM endpoint |
| `CONFLUENCE_*` | Confluence loader credentials |
| `SHAREPOINT_*` | SharePoint loader credentials (via Microsoft Graph) |
| `TICKET_PROVIDER` | `servicenow` / `jira` / `freshservice` |
| `CONFIDENCE_THRESHOLD` | Default `0.6` — tune empirically |
| `TICKET_MAX_AGE_DAYS` | Default `548` (~18 months) — discard older tickets |
| `API_SECRET_KEY` | Guards the `/ingest` admin endpoint |
| `ALLOWED_ORIGINS` | CORS allowlist for the FastAPI backend |

---

## Getting Started

```bash
# 1. Configure environment
cp .env.example .env
# Fill in all credentials

# 2. Start the database
docker compose up -d postgres

# 3. Run first-time full index
python scripts/reindex.py --full

# 4. Start the API
uvicorn api.main:app --reload

# 5. Start the UI
streamlit run frontend/app.py

# 6. (Optional) Run RAGAS evaluation
python -m app.evaluation.ragas_eval --golden tests/golden_set.json
```

---

## What Still Needs Doing Before Go-Live

- [ ] **Populate `tests/golden_set.json`** with ~50 real IT questions + known correct answers
- [ ] **Decide document permissions** — chatbot currently serves all indexed content to all users. If role-based access is required, add a user-group filter to `pgvector_store.similarity_search()`
- [ ] **Connect real ticketing system** — set `TICKET_PROVIDER` and confirm API credentials
- [ ] **Set up nightly cron** — `0 2 * * * python scripts/reindex.py >> logs/reindex.log 2>&1`
- [ ] **Wire up Teams bot** — register Azure Bot resource, set `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD`, point messaging endpoint at `/api/messages`
- [ ] **Tune `CONFIDENCE_THRESHOLD`** — run RAGAS eval and adjust empirically
- [ ] **Put a reverse proxy in front** of the FastAPI and Streamlit ports (nginx / App Gateway)
- [ ] **Configure audit log shipping** — `app/audit.py` writes structured JSON; point it at your SIEM

---

## Architecture Decisions (from Vera's spec)

| Decision | Rationale |
|---|---|
| pgvector over Qdrant/Pinecone | At 2k–5k vectors, purpose-built vector DBs add ops complexity with no perf benefit. pgvector gives native SQL metadata filtering + audit logging. |
| Manual retrieval (no LangChain) | Compliance obligations live here — must be auditable code the firm owns. |
| BM25 + dense hybrid | Dense catches semantic matches; BM25 catches exact terms (error codes, ticket numbers, product names). |
| Cross-encoder reranker | Biggest single accuracy lever in the pipeline. |
| `temperature=0.0` | Deterministic outputs required for auditability. |
| No auto-ticket submission | User reviews the draft — bot never takes external action autonomously. |
