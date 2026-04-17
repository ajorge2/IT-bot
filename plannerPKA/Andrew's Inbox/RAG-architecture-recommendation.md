# RAG Chatbot Architecture Recommendation
### IT Knowledgebase — Financial Firm
*Prepared by Vera — 2026-04-12*

---

## Context & Constraints
- **Sources:** Confluence, SharePoint, resolved tickets (ticketing system TBD)
- **Scale:** Hundreds of documents (~2,000–5,000 vectors after chunking)
- **Users:** Company-wide employees, self-service IT
- **Query types:** How-to, troubleshooting, policy lookup
- **Compliance:** Strict financial firm — data must not leave private cloud boundary
- **Accuracy:** Citation required on every response regardless of confidence
- **Failure mode:** Best-guess + disclaimer + source citation + auto-draft ticket on low confidence
- **Language:** Python
- **UI:** Own website (Teams bot as fallback)
- **Deployment:** Private cloud; compliant managed SaaS services acceptable

---

## Ingestion Pipeline

**Connectors — use LangChain document loaders:**
- Confluence → `LangChain ConfluenceLoader`
- SharePoint → `LangChain SharePointLoader` (via Microsoft Graph API)
- Tickets → whichever ticketing system API is confirmed; filter `status=resolved` at query time

**Chunking — use LangChain:**
- `RecursiveCharacterTextSplitter` at ~512 tokens with 50-token overlap
- Preserves section boundaries; overlap prevents answers being cut off at chunk edges

**Metadata to attach to every chunk:**
- `source_system` (confluence / sharepoint / tickets)
- `document_title`
- `source_url` (for citation)
- `last_updated` date
- `document_type` (how-to / policy / ticket resolution)

**Re-indexing:** Scheduled nightly job. Use source webhooks if available for fresher data.

---

## Embedding Model

**Recommendation:** Use the embedding endpoint your private LLM provider exposes (e.g., Azure OpenAI `text-embedding-3-small`, AWS Bedrock Titan Embeddings). Keeps all data inside your compliance boundary.

**Fallback (if no managed endpoint):** Self-host `BGE-large-en-v1.5` — open source, strong performance, no data leaves your infra.

**Ruled out:** Any SaaS embedding API that sends raw document text outside your private cloud.

---

## Vector Store

**Recommendation: `pgvector` on PostgreSQL**

At hundreds of documents (~2,000–5,000 vectors), a purpose-built vector database adds operational complexity with no performance benefit. pgvector gives you:
- Vector similarity search inside a database your team already knows how to operate and audit
- Native metadata filtering via SQL `WHERE` clauses (required for citation and freshness filtering)
- Native access control and audit logging (compliance requirement)
- No additional compliance surface area

*Alternative at scale:* If documents grow to tens of thousands, migrate to Qdrant (self-hostable, native hybrid search).

*Ruled out:* Pinecone, Weaviate Cloud (SaaS, data leaves environment); FAISS (library not database — no native metadata filtering, persistence, or audit logging).

---

## Retrieval Strategy

**Hybrid search: dense (vector) + sparse (BM25), then rerank.**

Write this yourself — do not delegate to LangChain:

1. **Dense retrieval:** pgvector cosine similarity — catches semantic matches
2. **Sparse retrieval:** `rank_bm25` (Python library) — catches exact term matches (error codes, product names, ticket numbers)
3. **Score fusion:** Combine dense + sparse scores (reciprocal rank fusion)
4. **Reranking:** `ms-marco-MiniLM-L-6-v2` cross-encoder (self-hostable) — re-scores top-K results before passing to LLM. Biggest single accuracy lever in the pipeline.
5. **Pass top 5 chunks to LLM**

---

## Generation

**LLM:** Whatever private endpoint you have access to. No architecture changes based on provider.

**System prompt (non-negotiable):**
```
Answer ONLY using the provided context documents.
If you are uncertain, state that clearly and add a disclaimer.
Always cite your source by document title and URL.
Do not invent information not present in the context.
```

**Write the prompt construction, LLM call, and response parsing yourself** — this is where your compliance obligations live and must be auditable code you own.

**Confidence handling:**
- If top retrieval score < 0.6 cosine similarity (tune empirically):
  1. Answer with best-guess + explicit disclaimer
  2. Cite closest source found
  3. Auto-generate a pre-filled ticket draft from the conversation summary — user reviews and submits

---

## Evaluation Framework

Use **RAGAS** (open source) measuring four metrics continuously:

| Metric | What it measures |
|---|---|
| Faithfulness | Is the answer grounded in retrieved chunks? |
| Answer Relevancy | Does it actually answer the question? |
| Context Precision | Did retrieval surface the right chunks? |
| Context Recall | Did retrieval miss anything important? |

Build a golden test set of ~50 real IT questions with known correct answers. Re-run eval after every ingestion pipeline change or model swap.

---

## UI & Deployment

- **Backend:** FastAPI
- **Frontend:** Streamlit to start; migrate to React if more UI control is needed
- **Teams bot fallback:** Microsoft Bot Framework SDK wraps the FastAPI backend — minimal rework when needed

---

## LangChain Usage Summary

| Component | Use LangChain? |
|---|---|
| Confluence document loader | Yes |
| SharePoint document loader | Yes |
| Chunking (RecursiveCharacterTextSplitter) | Yes |
| Retrieval (vector + BM25 + reranking) | No — write yourself |
| Prompt construction | No — write yourself |
| LLM call & response parsing | No — write yourself |
| Citation injection | No — write yourself |
| Confidence threshold + ticket draft | No — write yourself |

---

## Known Risks

| Risk | Mitigation |
|---|---|
| **Document permissions** — Confluence/SharePoint have role-based access. Does everyone get everything? | Decide before build. Simplest: chatbot serves only documents explicitly published to "all staff." |
| **Stale ticket data** — Old resolved tickets may contain outdated or wrong fixes | Add `last_updated` filter in retrieval — discard tickets older than 18–24 months |
| **Hallucination under grounding** | Citation requirement + reranker + threshold-gating are three layers of defense. No RAG system eliminates this — prompt and eval discipline minimize it. |
| **Re-indexing lag** | New content won't be searchable until next nightly run. Set user expectations. |
