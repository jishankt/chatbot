# Comprehensive Independent Audit Report — Citizen CX-02 Sales AI

**Document Version**: 1.0 (Final)  
**Date**: 2026-10-26  
**Auditor**: Principal Systems & Security Engineer (Independent Audit)  
**Target Repository**: `cx02-sales-ai` (Kepler Tech LLC, Dubai)  
**Repository State**: Read-Only Audit across code, database, tests, and runtime traces

---

## 1. Executive Summary

1. **Overall Architectural Grade**: **B- (Strong Foundation, Critical Go-Live Flaws)**.
2. **Deterministic Safety Posture**: Highly robust. Pre/post guardrails prevent competitor discussion (100% on benchmarks) and commercial hallucination.
3. **Primary Blocker #1 (Security)**: `GET /leads` (`app/api/routes.py:L84-L89`) is **completely unauthenticated**, exposing customer names, phone numbers, and notes.
4. **Primary Blocker #2 (WhatsApp Outbound)**: Inbound WhatsApp messages are parsed and logged, but **no outbound reply is ever dispatched**; `WHATSAPP_TOKEN` is unreferenced dead code.
5. **Primary Blocker #3 (Dead Code Architecture)**: The LLM generation module (`app/agent/llm.py`) is **never called** in `pipeline.py`; answers are generated via raw string slicing.
6. **Primary Blocker #4 (SKU Resolution Bug)**: `determine_target_sku()` defaults unconditionally to `"CX-02"`, pricing the 4,385 AED printer for unknown SKUs and accessories.
7. **Primary Blocker #5 (Evaluation Rigor)**: The 100% pass rate in `run_eval.py` is masked by tautological logic (`or len(chunks) > 0`); true top-1 RAG accuracy is only 38.0%.
8. **Commercial Data Accuracy**: Pricing and quotes strictly read `data/products.json` with zero arithmetic hallucinations, but Citizen Cleaning Pen price (190 AED vs 95 AED) remains unverified.
9. **Operational Freshness**: Policy handoffs properly trigger for null entries; price staleness logic correctly evaluates timestamps against configured limits.
10. **Recommendation**: Complete **Package NOW** remediation (auth on `/leads`, WhatsApp outbound sender, SKU default fix, quote comma parsing) prior to production customer traffic.

---

## 2. Findings Table

| ID | Severity | Area | Finding | Evidence (File:Lines or Command) | Impact | Remediation | Effort |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **CRITICAL** | Security | Unauthenticated PII Data Leak on `/leads` | `app/api/routes.py:L84-L89`: Route `/leads` returns all captured customer names and phones without any API key or session auth | Any anonymous internet user can scrape all captured customer leads | Add bearer token authentication (`Config.ADMIN_API_KEY`) or HMAC header check | S |
| **INT-01** | **HIGH** | WhatsApp | Outbound WhatsApp Replies Not Dispatched | `app/config.py:L38`, `app/api/routes.py:L134-L141`: `WHATSAPP_TOKEN` is defined but never used; no HTTP call made to Meta Graph API | Incoming WhatsApp queries are processed into SQLite, but the customer receives zero response | Implement `send_whatsapp_message()` calling `https://graph.facebook.com/v21.0/{phone_number_id}/messages` | M |
| **COR-01** | **HIGH** | Correctness | SKU Router Defaults Unconditionally to Base Printer | `app/agent/pipeline.py:L45`: `determine_target_sku()` returns `"CX-02"` for any unrecognized product query | Asking for "CX02-WIRELESS-ADAPTER" or invalid accessories returns 4,385.00 AED printer quote | Return `None` if no whitelisted SKU or alias matches; trigger unrecognized SKU handoff | S |
| **ARC-01** | **HIGH** | Architecture | LLM Response Generator is Dead Code in Pipeline | `app/agent/pipeline.py:L7`: `generate_llm_response` is imported but never invoked in `CX02Pipeline.process()` | System operates as pure deterministic string slicer (`lines[:5]`); Ollama model tag mismatch (`qwen2.5:7b` vs `latest`) is hidden | Wire `generate_llm_response` into knowledge synthesis with validator gating, or formalize deterministic architecture | M |
| **TST-01** | **HIGH** | Testing | Evaluation Benchmark Has Tautological Pass Assertion | `eval/run_eval.py:L136`: `rag_hit = (exp_sec in retrieved_sections) or len(chunks) > 0` | 62% of RAG questions retrieve irrelevant sections yet pass evaluation; strict top-1 accuracy is only 38.0% | Remove `or len(chunks) > 0`; require `chunks[0]['section'] == exp_sec` | S |
| **COR-02** | **MEDIUM** | Correctness | Quotation Quantity Regex Truncates Comma Numbers | `app/agent/pipeline.py:L241`: `re.search(r"\b(\d+)\b", user_msg)` matches `"5"` for `"5,000"` | Customer asking for quote on "5,000" units gets a quote for 5 units instead of triggering >1,000 handoff | Use `re.search(r"\b(\d[\d,]*)\b")` and strip commas before parsing integer | S |
| **SEC-02** | **MEDIUM** | Security | WhatsApp Signature Verification Skipped If Secret Blank | `app/api/routes.py:L103`: `if Config.WHATSAPP_APP_SECRET:` only validates when variable is truthy | If environment variable is missing, webhook accepts unauthenticated, spoofed Meta payloads | Fail closed: reject requests if `WHATSAPP_APP_SECRET` is unset in production | S |
| **SEC-03** | **MEDIUM** | Security | Unbounded Message Payload Length (No Input Truncation) | `app/agent/pipeline.py:L70`: `user_msg = user_message.strip()` | Adversary can send 10MB payload causing CPU denial of service during regex matching | Truncate `user_message` to 1,000 characters at API controller boundary | S |
| **LOG-01** | **LOW** | Operability | JSONL Audit Logger Defined but Never Invoked | `app/audit_logging/audit.py:L10`: `def log_turn(...)` is never referenced in `pipeline.py` or `routes.py` | `data/audit.jsonl` is not updated during conversation turns; records only exist in SQLite | Call `log_turn()` inside `pipeline.process()` upon turn completion | S |
| **ROU-01** | **LOW** | Correctness | Router Fragility Under Realistic Phrasing & Slang | `scripts/audit/eval_audit.py`: 12 of 30 mutated questions failed intent routing (e.g., "best rate", "red light error") | Realistic customer questions fall through to generic overview or wrong price tool | Add fuzzy keyword matching or expanded regex patterns for UAE commercial terms | M |

---

## 3. Verdicts on Known Concerns (A through M)

### A. VAT Configuration
- **Verdict**: **VERIFIED AS SPECIFIED**.
- **Evidence**: `app/config.py:L26-L29` defaults `VAT_RATE = None` and `PRICES_INCLUDE_VAT = None`. In `app/tools/quote.py:L74-L88`, when both are not set, `vat_amount = None` and output displays `"VAT: Consult sales desk for applicable tax treatment"`.
- **Note**: Customer query *"Do your prices include 5% UAE VAT or is tax extra?"* was misrouted to `price` tool due to the word "prices", rather than `policies`.

### B. Cleaning Pen Price
- **Verdict**: **UNRESOLVED COMMERCIAL CONFLICT**.
- **Evidence**: `data/products.json:L75-L79` sets price to 190.00 AED with note *"Kepler page lists 190 AED; another document notes 95 AED"*. In `eval/questions.jsonl:L98-L101`, questions expected 95.00 AED.
- **Finding**: Kepler Tech LLC must provide signed commercial confirmation on whether the retail price is 190.00 AED or 95.00 AED.

### C. Print Counts per Media Set
- **Verdict**: **VERIFIED AS SPECIFIED**.
- **Evidence**: `data/products.json:L30, L43, L56`: 4x6" (800 prints) and 6x8" (400 prints) have `"prints_verified": false` and `"estimate_note": "Estimate based on 2 rolls..."`. 5x7" (460 prints) has `"prints_verified": true` and `"estimate_note": null`.
- **Finding**: Output templates in `app/tools/pricing.py:L195-L207` explicitly print estimate disclaimers.

### D. Price Freshness & Stock Semantics
- **Verdict**: **VERIFIED WITH MINOR GAP**.
- **Evidence**: `app/tools/pricing.py:L49-L59` computes `(today - as_of_dt).days > max_age_days`. If stale, appends warning: *"Prices shown are as of {as_of}. Please confirm current rates..."*.
- **Gap**: Stock is tracked as a static boolean flag (`"in_stock": true` in `products.json`), not real-time inventory counts.

### E. Policy Handoffs
- **Verdict**: **VERIFIED AS SPECIFIED**.
- **Evidence**: `data/policies.json:L9-L16` contains `null` for warranty, delivery time, delivery charges, payment methods, returns, installation, support, and VAT.
- **Finding**: `app/tools/policies.py:L43-L54` returns `status: "unknown"` and `handoff: true`, directing customers to Kepler's Dubai phone number (`00971 4 323 1008`).

### F. LLM Dependency & Graceful Fallback
- **Verdict**: **DEFECT DETECTED (DEAD CODE ARCHITECTURE)**.
- **Evidence**: `app/agent/llm.py:L20-L77` contains full Ollama client code with fallback, but `app/agent/pipeline.py:L7` only imports `generate_llm_response` and never calls it.
- **Finding**: In `pipeline.py:L278-L287`, the response is built by extracting lines 1–5 of the top chunk directly: `"\n".join(lines[:5])`. Furthermore, `app/config.py:L33` specifies `qwen2.5:7b`, which does not exist in local Ollama (local model tag is `qwen2.5:latest`), returning HTTP 404 if called.

### G. Retrieval Quality & Hybrid BM25
- **Verdict**: **FUNCTIONAL BUT LOW STRICT ACCURACY**.
- **Evidence**: `app/rag/retriever.py:L1-L125` uses `rank_bm25.BM25Okapi` with score threshold $\ge 0.05$ and coverage $\ge 25\%$.
- **Finding**: Under `scripts/audit/eval_audit.py`, loose pass rate is 100%, but strict top-1 section match is only **38.0% (19/50)**. Questions about print resolution retrieved ribbon rewind chunks.

### H. Post-Guardrail Checks
- **Verdict**: **VERIFIED AS SPECIFIED**.
- **Evidence**: `app/agent/guardrails.py:L130-L147` scans output text for 7 competitor brands and non-CX-02 Citizen models. `app/agent/validator.py:L41-L92` checks for ungrounded numbers, prices, and commercial terms.
- **Finding**: Zero competitor leakages detected across 220 benchmark runs and 48 adversarial probes.

### I. Eval Trustworthiness & Phrasing Circularity
- **Verdict**: **EVAL RIGOR DEFECT DETECTED**.
- **Evidence**: `eval/run_eval.py:L136` uses `rag_hit = (exp_sec in retrieved_sections) or len(chunks) > 0`.
- **Finding**: 28.6% of benchmark questions share $\ge 5$ contiguous words with raw documentation. The loose OR condition creates artificial 100% metrics.

### J. WhatsApp Webhook Security & Deduplication
- **Verdict**: **INCOMPLETE INTEGRATION (INGRESS OK, OUTBOUND MISSING)**.
- **Evidence**: Ingress validates HMAC-SHA256 via `hmac.compare_digest` (`routes.py:L111-L113`) and deduplicates via `is_message_duplicate(msg_id)` in SQLite (`routes.py:L127`).
- **Finding**: Outbound sender client is missing. Messages are received and logged, but no response is sent back to WhatsApp users.

### K. Data Protection & Plaintext PII
- **Verdict**: **SECURITY DEFECT DETECTED**.
- **Evidence**: Customer phone numbers, names, and chat logs are stored unencrypted in `data/sales_ai.db`. Route `GET /leads` (`routes.py:L84`) exposes all customer records to unauthenticated callers.
- **Finding**: Critical GDPR/UAE PDPL privacy compliance risk.

### L. Session Handling & Follow-ups
- **Verdict**: **LIMITED MULTI-TURN ROBUSTNESS**.
- **Evidence**: `pipeline.py:L76` fetches last 8 turns from SQLite, but `classify_intent` only inspects `user_msg`.
- **Finding**: Follow-up "And how much is it in AED?" succeeded because "how much" triggered the price router, but "And the 5x7?" failed (classified as RAG, missing tool invocation).

### M. Quotation Quantity Limits & Arithmetic
- **Verdict**: **ARITHMETIC SOLID; INPUT PARSING BUG FOUND**.
- **Evidence**: `app/tools/quote.py:L53-L58` strictly enforces $1 \le \text{qty} \le 1000$ and calculates floating-point totals rounded to 2 decimals.
- **Finding**: `pipeline.py:L241` uses `\b(\d+)\b`, parsing `"5,000"` as `5`, which bypassed the upper bound guard.

---

## 4. What is Done Well

1. **Zero Arithmetic / Pricing Hallucinations**: Across 220 benchmark tests and 48 adversarial probes, the assistant **never invented a single price or made an arithmetic calculation error**. All figures are generated deterministically from `products.json`.
2. **Robust Competitor Brand Rejection**: Input and output guardrails reliably block inquiries regarding DNP, Epson, Fujifilm, HiTi, Sinfonia, Mitsubishi, and unauthorized Citizen models (CX-02W, CZ-01, CY-02) with 100% precision.
3. **Graceful Policy Handoff**: Rather than hallucinating warranty or return terms, the system reliably falls back to Kepler Tech's human sales contact details.
4. **Deterministic Architecture Stability**: Sub-20 millisecond response times and zero external API failure dependencies under current deployment.
5. **Clean SQLite Schema & Persistence**: Tables for messages, quotes, handoffs, and leads have clean foreign keys, indices, and auto-migration logic.
