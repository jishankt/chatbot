import os, sys, json

audit_dir = "/opt/basics/audit"
os.makedirs(audit_dir, exist_ok=True)

# -------------------------------------------------------------
# 01_ARCHITECTURE.md
# -------------------------------------------------------------
arch_content = """# 01_ARCHITECTURE.md - System Architecture & Structural Analysis

## 1. Architectural Style & High-Level Design
The **Kepler Tech CX-02 Sales AI** system is architected as a **Dual-Track Cognitive Sales Agent** combining deterministic finite-state rule processing with retrieval-augmented generation (RAG) and large language model (LLM) phrasing.

### Architectural Archetype
* **Style:** Layered Modular Monolith with Finite State Machine (FSM) & Dual-Track Arbitration.
* **Process Model:** Synchronous WSGI web application served by Gunicorn (`2` worker processes in production) with SQLite WAL database.
* **Core Philosophy (Hard Rules 1 & 2):** Strict commercial separation of authority. The LLM is strictly forbidden from inventing prices, stock, delivery, or warranty data. All commercial figures originate deterministically from canonical data files (`data/products.json`, `data/policies.json`) via tools, validated claim-by-claim by `app/agent/validator.py`.

```mermaid
graph TD
    User([Customer / Client]) <-->|HTTP / Webhook| Gateway[Reverse Proxy / Gunicorn]
    Gateway <--> FlaskApp[Flask Application app/main.py]
    
    subgraph "API & Guardrail Layer"
        FlaskApp --> Routes[app/api/routes.py]
        Routes --> PreGuard[Pre-Guardrails app/agent/guardrails.py]
    end

    subgraph "Cognitive Pipeline (app/cognitive/)"
        PreGuard --> Reader[Reader: Normalization & Entities]
        Reader --> Understander[Understander: Rule Intent + LLM NLU]
        Understander --> StateMachine[State Machine: Sales FSM & Context]
    end

    subgraph "Execution & Retrieval"
        StateMachine --> Router[Priority Router app/agent/router.py]
        Router --> Pipeline[Agent Pipeline app/agent/pipeline.py]
        Pipeline --> Tools[Commercial Tools: Pricing, Quotes, Leads]
        Pipeline --> RAG[Hybrid RAG: BM25 + TF-IDF Cosine app/rag/]
    end

    subgraph "Generation & Validation"
        RAG --> LLM[LLM Generator: OpenRouter / Ollama]
        LLM --> Validator[Claim Validator app/agent/validator.py]
        Validator --> PostGuard[Post-Guardrails & Leak Checks]
        PostGuard --> AuditLog[HMAC Audit Logger app/audit_logging/]
    end

    subgraph "Persistence Layer"
        Tools --> SQLite[(SQLite WAL: sales_ai.db)]
        StateMachine --> SQLite
        AuditLog --> AuditFile[(data/audit.jsonl)]
    end
```

---

## 2. Module Dependency Graph & Coupling Analysis

```mermaid
graph LR
    subgraph Core
        main[app.main] --> routes[app.api.routes]
        main --> config[app.config]
    end

    subgraph Orchestration
        routes --> pipeline[app.agent.pipeline]
        pipeline --> reader[app.cognitive.reader]
        pipeline --> understander[app.cognitive.understander]
        pipeline --> statemachine[app.cognitive.state_machine]
        pipeline --> router[app.agent.router]
        pipeline --> llm[app.agent.llm]
        pipeline --> validator[app.agent.validator]
        pipeline --> tools[app.tools.*]
    end

    subgraph RAG
        pipeline --> retriever[app.rag.retriever]
        retriever --> chunker[app.rag.chunker]
        retriever --> hybrid[app.rag.hybrid]
    end

    subgraph Storage
        pipeline --> db[app.storage.db]
        routes --> db
        statemachine --> db
        tools --> db
    end
```

### Layering Violations & Circular Risks
1. **Monolithic God-Module (`app/agent/pipeline.py`):**
   * Spans **2,245 lines** and 158 KB.
   * Directly imports across almost every layer: `app.agent.router`, `app.agent.validator`, `app.agent.guardrails`, `app.cognitive.*`, `app.rag.*`, `app.storage.*`, `app.tools.*`, and `app.whatsapp.*`.
   * Directly handles pricing calculations, discount negotiation policies, RAG fallback formatting, lead generation, conflict resolution, and UI cards generation.
2. **Circular Dependency Mitigations:**
   * Deferred inline imports (`from app.tools.quote import create_quote` inside route functions or methods) are used extensively across `app/api/routes.py` (e.g. lines 231, 342, 370, 402, 433) and `app/agent/pipeline.py` to prevent cyclic import deadlocks at boot time.
3. **Double Storage Boundary:**
   * Conversation state is saved in both `conversation_states` table (via `app/cognitive/state_machine.py`) and `messages` table (via `app/storage/messages.py`) without a unified database transaction.

---

## 3. External Integrations & Boundaries
| Integration | Module / File | Transport / Protocol | Authentication | Timeout / Failover |
| :--- | :--- | :--- | :--- | :--- |
| **OpenRouter LLM API** | `app/agent/llm.py:34-58` | HTTPS POST JSON | Bearer token (`OPENROUTER_API_KEY`) | 15.0s timeout; falls back to local Ollama |
| **Ollama Local LLM** | `app/agent/llm.py:59-78` | HTTP POST JSON | None (localhost:11434) | 15.0s timeout; falls back to extractive template |
| **Meta WhatsApp API** | `app/whatsapp/client.py` | HTTPS POST Graph API | Bearer token (`WHATSAPP_TOKEN`) | Fail-closed in prod if secret missing |
| **SQLite WAL DB** | `app/storage/db.py` | Local filesystem POSIX | File permissions (600/644) | 15.0s busy_timeout with WAL journal |
| **Prometheus Metrics**| `app/api/routes.py:221-228`| HTTP GET | Protected by Bearer `ADMIN_API_KEY` | In-memory atomic counters |

---

## 4. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    MESSAGES {
        int id PK
        string message_id UK
        string sender_id
        string channel
        string role
        string content
        string reply_source
        string fallback_reason
        int is_test
        timestamp created_at
    }

    CONVERSATION_STATES {
        string sender_id PK
        string current_state
        int turn_count
        string business_type
        string delivery_destination
        string target_sku
        string quote_id
        string discovery_questions_asked
        string last_intent
        int version
        int quantity
        real budget
        string language
        string current_product
        string rolling_summary
        string slots_json
        timestamp updated_at
    }

    LEADS {
        int id PK
        string sender_id
        string name
        string phone
        string email
        string notes
        string status
        timestamp created_at
    }

    QUOTES {
        int id PK
        string quote_id UK
        string sender_id
        string customer_name
        string phone
        string items_json
        real subtotal
        real vat_amount
        real total
        int subtotal_fils
        int vat_fils
        int total_fils
        string catalog_version
        timestamp expires_at
        timestamp created_at
    }

    HANDOFFS {
        int id PK
        string sender_id
        string reason
        string summary
        string phone
        string status
        string notification_status
        timestamp notification_sent_at
        string notification_error
        int retry_count
        timestamp created_at
    }

    ADMIN_AUTH_FAILURES {
        int id PK
        string ip
        string endpoint
        timestamp attempt_time
    }

    LLM_GENERATION_LEASES {
        string lease_id PK
        string worker_id
        real acquired_at
        real expires_at
    }

    CONVERSATION_STATES ||--o{ MESSAGES : "generates"
    CONVERSATION_STATES ||--o{ QUOTES : "creates"
    CONVERSATION_STATES ||--o{ LEADS : "captures"
    CONVERSATION_STATES ||--o{ HANDOFFS : "escalates"
```

---

## 5. End-to-End Runtime Sequence Flows

### Flow A: Inbound Customer Chat Request (/chat)
```mermaid
sequenceDiagram
    autonumber
    actor Customer
    participant Nginx as Reverse Proxy
    participant Flask as Flask App (routes.py)
    participant Pipeline as CX02Pipeline
    participant Cog as Cognitive (Read/Understand/Think)
    participant RAG as RAG / Tools
    participant LLM as LLM / Extractive
    participant Val as Validator
    participant DB as SQLite DB

    Customer->>Nginx: POST /chat {message, sender_id}
    Nginx->>Flask: Forward request + X-Forwarded-For
    Flask->>Flask: Verify/issue signed web_session_id cookie
    Flask->>Pipeline: pipeline.process(user_message, sender_id)
    Pipeline->>Cog: 1. read_message() -> ReadContext
    Pipeline->>Cog: 2. understand_message() -> UnderstandResult
    Pipeline->>Cog: 3. transition_sales_state() -> Decision
    
    alt Guardrail Triggered
        Pipeline->>Pipeline: Early return guardrail template
    else Tool Call Required (Price / Stock / Quote)
        Pipeline->>RAG: Call pricing / quote tools
        RAG->>DB: Read catalog / insert quote
    else Technical Knowledge Inquiry
        Pipeline->>RAG: retrieve(query, top_k=2)
        Pipeline->>LLM: generate_llm_response(chunks, facts)
        LLM->>Val: validate_response(llm_output, chunks, tools)
        alt Validation Fails
            Val->>LLM: Retry with feedback or fallback to extractive template
        end
    end

    Pipeline->>DB: log_message(user), log_message(assistant)
    Pipeline->>DB: save_sales_state()
    Pipeline-->>Flask: Response dict {reply, intent, cards, latency_ms}
    Flask-->>Customer: HTTP 200 JSON
```

### Flow B: Specialist Handoff & CRM Lead Capture
```mermaid
sequenceDiagram
    autonumber
    actor Customer
    participant Pipeline
    participant Tools as Lead / Handoff Tools
    participant DB as SQLite DB
    participant Audit as Audit Logger

    Customer->>Pipeline: "Can someone call me? My phone is +971501234567"
    Pipeline->>Pipeline: Match human_demo_reserve or lead capture
    Pipeline->>Tools: extract_phone_and_name(message)
    Pipeline->>Tools: create_lead(name, phone, sender_id)
    Tools->>DB: INSERT INTO leads (sender_id, name, phone, notes)
    Pipeline->>Tools: handoff_to_human(reason, phone, sender_id)
    Tools->>DB: INSERT INTO handoffs (sender_id, reason, phone, status='pending')
    Pipeline->>Audit: audit_event("LEAD_CAPTURED", hmac_signature)
    Audit->>DB: Append to data/audit.jsonl
    Pipeline-->>Customer: Deterministic handoff response with Dubai showroom details
```
"""

with open(os.path.join(audit_dir, "01_ARCHITECTURE.md"), "w") as fp:
    fp.write(arch_content.strip() + "\n")
print("01_ARCHITECTURE.md created.")

# -------------------------------------------------------------
# 03_API_INVENTORY.md
# -------------------------------------------------------------
api_content = """# 03_API_INVENTORY.md - Comprehensive Endpoint & RPC Audit

This inventory catalogues every route registered in the application, its handler, HTTP method, authentication enforcement, input validation, and risk profile.

## API Endpoint Matrix

| Method | Endpoint Path | Handler Function | Auth Required | Input Validation | Rate Limited | Status Codes | Data Access | Risk Rating |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | `test_page()` (`routes.py:154`) | None | None | No | 200 | Static template render | **Low** |
| `GET` | `/test` | `test_page()` (`routes.py:155`) | None | None | No | 200 | Static template render | **Low** |
| `POST`| `/chat` | `chat_endpoint()` (`routes.py:234`) | Session Cookie or `sender_id` | Max length, empty check | No app-level limit | 200, 400, 500 | `messages`, `conversation_states`, `leads`, `quotes` | **Medium** |
| `POST`| `/quote` | `quote_endpoint()` (`routes.py:335`) | None | Name regex, item list check | No | 200, 400 | `quotes` table | **Medium** |
| `GET` | `/history` | `history_endpoint()` (`routes.py:376`)| Session Cookie OR Admin Bearer | Limit integer clamped (50-100)| No | 200, 400, 401 | `messages` table | **HIGH (IDOR)** |
| `GET` | `/chat/history`| `history_endpoint()` (`routes.py:377`)| Session Cookie OR Admin Bearer | Limit integer clamped (50-100)| No | 200, 400, 401 | `messages` table | **HIGH (IDOR)** |
| `GET` | `/history/export`| `export_history_endpoint()` (`routes.py:411`)| Session Cookie OR Admin Bearer | Parameter format check | No | 200, 400, 401 | `messages` table | **HIGH (IDOR)** |
| `GET` | `/leads` | `leads_endpoint()` (`routes.py:358`) | **Admin Bearer / X-Admin-Key** | Limit clamped (100) | Lockout on 5 fails | 200, 401, 429 | `leads` table | **Medium** |
| `GET` | `/handoffs` | `handoffs_endpoint()` (`routes.py:366`) | **Admin Bearer / X-Admin-Key** | Limit query param | Lockout on 5 fails | 200, 401, 429 | `handoffs` table | **Medium** |
| `GET` | `/health` | `health_check()` (`routes.py:161`) | None (Public) | None | No | 200, 503 | DB `SELECT 1`, filesystem checks | **Low** |
| `GET` | `/healthz` | `healthz_endpoint()` (`routes.py:214`)| **Admin Bearer / X-Admin-Key** | None | Lockout on 5 fails | 200, 401, 429, 503 | DB, filesystem checks | **Low** |
| `GET` | `/metrics` | `metrics_endpoint()` (`routes.py:221`)| **Admin Bearer / X-Admin-Key** | None | Lockout on 5 fails | 200, 401, 429 | In-memory atomic counters | **Low** |
| `POST`| `/admin/unlock`| `admin_unlock_endpoint()` (`routes.py:121`)| **Admin Bearer / X-Admin-Key** | IP string required | Lockout on 5 fails | 200, 400, 401, 429 | `admin_auth_failures` DELETE | **Medium** |
| `GET` | `/webhook` | `webhook_get()` (`routes.py:509`) | WhatsApp Hub Token | Hub challenge parameters | No | 200, 403 | None | **Low** |
| `GET` | `/webhook/whatsapp` | `webhook_get()` (`routes.py:510`) | WhatsApp Hub Token | Hub challenge parameters | No | 200, 403 | None | **Low** |
| `POST`| `/webhook` | `webhook_post()` (`routes.py:515`) | HMAC-SHA256 (`X-Hub-Signature-256`) | Meta entry/changes JSON schema | No | 200, 401, 403, 500 | Full agent pipeline, DB | **Medium** |
| `POST`| `/webhook/whatsapp`| `webhook_post()` (`routes.py:516`) | HMAC-SHA256 (`X-Hub-Signature-256`) | Meta entry/changes JSON schema | No | 200, 401, 403, 500 | Full agent pipeline, DB | **Medium** |

---

## Detailed Endpoint Breakdown

### 1. `POST /chat`
* **Evidence:** `app/api/routes.py:234-332`
* **Authentication:** Dual-mode:
  1. Signed cookie `web_session_id` using HMAC-SHA256 (`app/utils/session.py`).
  2. Direct `sender_id` parameter accepted without cookie if prefix is `test_`, `user_`, or `proc_`.
* **Input Validation:**
  * Checks for empty message (`routes.py:243`).
  * Enforces maximum character length (`Config.MAX_MESSAGE_LENGTH = 1000` chars) (`routes.py:247`).
* **Error Handling:**
  * Unhandled exceptions in the agent pipeline are caught in a `try/except Exception` block (`routes.py:284-298`) and return an HTTP 200 graceful fallback message with Dubai sales desk contact information.

### 2. `GET /history` & `GET /history/export` (IDOR Vulnerability)
* **Evidence:** `app/api/routes.py:376-442`
* **Authentication Flaw:**
  ```python
  # app/api/routes.py:389-392
  else:
      requested = request.args.get("sender_id", "").strip()
      if requested and (requested.startswith("test_") or requested.startswith("user_") or requested.startswith("proc_")):
          sender_id = requested
  ```
* **Impact:** Any unauthenticated caller can supply `?sender_id=user_victim` and bypass session isolation, reading the complete chat transcript and decrypted message history of other users.

### 3. `POST /admin/unlock` & IP Lockout Bypass
* **Evidence:** `app/api/routes.py:37-41`, `121-152`
* **Mechanism:** Tracks repeated failed admin attempts in table `admin_auth_failures`. When `COUNT >= 5` in 15 minutes, returns HTTP 429.
* **Spoofing Vulnerability:**
  ```python
  # app/api/routes.py:37-41
  def get_client_ip() -> str:
      xff = request.headers.get("X-Forwarded-For", "")
      if xff:
          return xff.split(",")[0].strip()
      return request.headers.get("X-Real-IP") or request.remote_addr or "127.0.0.1"
  ```
* **Impact:** The code reads the raw untrusted `X-Forwarded-For` header rather than sanitized WSGI environment `request.remote_addr`. An attacker can rotate spoofed IPs in the header to evade lockout indefinitely.
"""

with open(os.path.join(audit_dir, "03_API_INVENTORY.md"), "w") as fp:
    fp.write(api_content.strip() + "\n")
print("03_API_INVENTORY.md created.")

# -------------------------------------------------------------
# 07_BACKEND_REPORT.md
# -------------------------------------------------------------
backend_content = """# 07_BACKEND_REPORT.md - Deep-Dive Backend, Data, Concurrency & Runtime Audit

## 1. Runtime & Server Architecture
* **Framework:** Flask 3.1.3 on Python 3.12.3.
* **WSGI Execution:** Gunicorn 26.2.0 synchronous multi-process model (`-w 2` workers configured in Dockerfile).
* **Async / Concurrency Model:** Single-threaded synchronous execution per worker process.
* **Thread / Process Blocking Hazards:**
  * LLM generation (`app/agent/llm.py:49` and `app/agent/llm.py:72`) performs blocking synchronous `requests.post()` calls with up to **15.0s timeout**.
  * Under concurrent traffic, if two requests trigger LLM calls simultaneously, both Gunicorn worker processes become blocked waiting on HTTP responses, starving the server and queuing all subsequent incoming connections.

---

## 2. Middleware & Interceptor Pipeline
The execution pipeline is evaluated in the following deterministic sequence:

1. **`werkzeug.middleware.proxy_fix.ProxyFix` (`app/main.py:28`):**
   * Configured with `x_for=1, x_proto=1, x_host=1, x_prefix=1`.
   * Replaces `request.remote_addr` with the immediate proxy hop.
   * *Flaw:* `app/api/routes.py:get_client_ip()` bypasses `ProxyFix` by directly inspecting the raw `request.headers.get("X-Forwarded-For")`.
2. **`require_admin_auth` Decorator (`app/api/routes.py:84-118`):**
   * Intercepts administrative endpoints (`/leads`, `/handoffs`, `/metrics`, `/healthz`).
   * Validates `Authorization: Bearer <token>` or `X-Admin-Key` header against `Config.ADMIN_API_KEY` using constant-time `hmac.compare_digest`.
   * Queries SQLite table `admin_auth_failures` on every request.
   * *Flaw:* Repeated queries to SQLite for failure count on every admin request without an in-memory cache.
3. **Session Cookie Isolation (`app/api/routes.py:254-270`):**
   * Inspects `web_session_id` cookie signed with HMAC-SHA256 (`app/utils/session.py`).
   * Emits `HttpOnly`, `SameSite=Lax`, and `Secure` (production only) flags.

---

## 3. Database Schema, Constraints & Concurrency

### Database Configuration (`app/storage/db.py:209-224`)
```python
conn = sqlite3.connect(str(path), timeout=15.0)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=15000;")
conn.execute("PRAGMA foreign_keys=ON;")
conn.execute("PRAGMA synchronous=NORMAL;")
```
* **Pros:** Write-Ahead Logging (`WAL`) allows concurrent readers and single writer without blocking readers.
* **Cons & Risks:**
  1. **No Connection Pool:** Every database function opens a brand new SQLite connection and closes it immediately (`conn = get_db_connection() ... finally: conn.close()`).
  2. **Metadata Introspection Overhead:** Functions like `log_message` (`app/storage/messages.py:32`) and `get_conversation_history` (`app/storage/messages.py:74`) execute `PRAGMA table_info(messages)` on **every single invocation**.
  3. **Optimistic Locking Race Condition:**
     * In `app/cognitive/state_machine.py:205-210`:
       ```python
       cur.execute("SELECT version FROM conversation_states WHERE sender_id = ?", (state.sender_id,))
       existing = cur.fetchone()
       if existing:
           state.version = existing["version"]
           continue
       ```
     * When a version conflict occurs, the code reloads the version counter and immediately retries the update with the stale in-memory state, overwriting concurrent turn updates (Lost Update Anomaly).

---

## 4. Multi-Tenancy & Data Isolation Audit
* **Isolation Strategy:** Partitioned by `sender_id`.
* **Vulnerability Analysis:**
  * In `app/api/routes.py:259` and `app/api/routes.py:390`, any input `sender_id` starting with `user_`, `test_`, or `proc_` completely bypasses cookie-based session verification.
  * An attacker can forge `GET /history?sender_id=user_target` or `POST /chat` with `{"sender_id": "user_target"}` and intercept or corrupt the victim's session state.
"""

with open(os.path.join(audit_dir, "07_BACKEND_REPORT.md"), "w") as fp:
    fp.write(backend_content.strip() + "\n")
print("07_BACKEND_REPORT.md created.")

# -------------------------------------------------------------
# 08_AI_REPORT.md
# -------------------------------------------------------------
ai_content = """# 08_AI_REPORT.md - AI, LLM, RAG & NLP Systems Audit

## 1. AI Touchpoint Inventory & Architecture
* **Primary Cloud Model:** OpenRouter API (`https://openrouter.ai/api/v1`) using `meta-llama/llama-3.3-70b-instruct` (`app/config.py:39`).
* **Fallback Local Model:** Ollama API (`http://localhost:11434`) using `qwen2.5:7b` (`app/config.py:42`).
* **Embedding Model:** Ollama `nomic-embed-text` (`app/config.py:43`) combined with BM25 Okapi (`rank-bm25`) and TF-IDF Cosine reranking (`app/rag/hybrid.py`).
* **Orchestration Paradigm:** Deterministic State Machine + Extractive Tool Grounding + LLM Semantic Phrasing.

```mermaid
graph TD
    UserQuery[User Message] --> PreGuard[Pre-Guardrails Filter]
    PreGuard --> NLU[LLM NLU / Rule Understander]
    NLU --> FSM[Sales State Machine Thinker]
    FSM --> Router[Priority Router]
    
    subgraph "Commercial Data Boundary (Hard Rule 1)"
        Router -->|Fact Query| Tools[Pricing & Spec Tools]
        Tools -->|Exact Verified JSON| ContextAssembly[Context Assembler]
    end

    subgraph "Knowledge Retrieval (RAG)"
        Router -->|Technical Inquiry| HybridRetriever[BM25 + TF-IDF Reranker]
        HybridRetriever --> ContextAssembly
    end

    ContextAssembly --> LLMGen[LLM Phrasing Call: OpenRouter / Ollama]
    LLMGen --> Validator[Claim & Number Validator]
    Validator -->|Pass| Output[Validated Reply]
    Validator -->|Fail| Extractive[Extractive Deterministic Template]
```

---

## 2. Complete Prompt Inventory

### Prompt 1: LLM Phrasing System Prompt
* **Location:** `app/agent/llm.py:10-26`
* **Purpose:** Instructs the LLM on persona, brevity, and grounding constraints.
* **Text Extract:**
  ```text
  You are the official Kepler Tech sales consultant for Kepler Tech LLC (Dubai)...
  STRICT FACTUAL CONSTRAINTS:
  1. Answer ONLY using the verified facts and retrieved context chunks provided below.
  2. If the context does not explicitly contain the answer, reply with 'NO_ANSWER'.
  3. NEVER guess, estimate, or invent numbers, dimensions, speeds, weights, warranties...
  6. When stating prices or yields, quote the exact figures from the verified facts...
  ```
* **Critical Finding (Hard Rule Violation):**
  * Line 25 contains hardcoded price strings: `4,385.00 AED for CX-02, 490.00 AED for 4x6 media, 500.00 AED for 5x7 media...`.
  * Violates Hard Rule 1 (commercial authority strictly from tools) and Hard Rule 4 (configuration-driven scope).

### Prompt 2: Structured NLU Extraction Prompt
* **Location:** `app/cognitive/understander.py:299-327`
* **Purpose:** Forces JSON schema output for intent, sentiment, business type, and risk flags.
* **Schema Definition:**
  ```json
  {
    "primary_intent": "string",
    "sub_intent": "string or null",
    "commercial_readiness": "high" | "medium" | "low",
    "business_type": "photobooth" | "studio" | "freelance" | "kiosk" | "event" | "unknown",
    "delivery_destination": "UAE" | "GCC" | "outside_gcc" | null,
    "sentiment": "positive" | "neutral" | "negative" | "frustrated",
    "urgency": "urgent" | "normal",
    "risk_flags": {
      "competitor_mentioned": boolean,
      "churn_risk": boolean,
      "anger_frustration": boolean,
      "legal_threat": boolean,
      "prompt_injection": boolean
    }
  }
  ```

---

## 3. OWASP Top 10 for LLM Applications Mapping

| OWASP LLM ID | Vulnerability Category | Repository Implementation Status & Finding | Severity |
| :--- | :--- | :--- | :--- |
| **LLM01** | Prompt Injection | **Protected (Dual Gate):** Pre-guardrail regex patterns (`app/agent/guardrails.py:10-52`) check for system prompt extraction, jailbreaks, and delimiter bypass. Post-guardrail checks output. | **Low** |
| **LLM02** | Insecure Output Handling | **Protected:** Output validator (`app/agent/validator.py:52-120`) scans for ungrounded numbers, prices, and banned claims. Falls back to extractive template. | **Low** |
| **LLM03** | Training Data Poisoning | **Not Applicable:** No model training or fine-tuning performed on customer data. | **Info** |
| **LLM04** | Model Denial of Service | **Vulnerable:** Admission queue (`app/agent/admission.py`) uses DB leases, but HTTP requests block WSGI threads for 15s. Burst traffic can exhaust Gunicorn workers. | **Medium** |
| **LLM05** | Supply Chain Risks | **Medium Risk:** Unpinned OpenRouter model string `meta-llama/llama-3.3-70b-instruct` can change underlying weights without notice. | **Low** |
| **LLM06** | Sensitive Information Disclosure | **Protected:** PII masking (`mask_phone_number`), field encryption for messages, system prompt leak detection regexes in post-guardrails. | **Low** |
| **LLM07** | Insecure Plugin Design | **Protected:** Tools (`pricing.py`, `quote.py`, `leads.py`) are strictly parameter-checked and have no arbitrary shell/network access. | **Low** |
| **LLM08** | Excessive Agency | **Protected:** Tools cannot execute financial transactions, send unsolicited external messages, or delete data. | **Low** |
| **LLM09** | Overreliance | **Protected:** Deterministic circuit breaker and dual-track arbitration strictly overrides LLM outputs on commercial data. | **Low** |
| **LLM10** | Model Theft | **Not Applicable:** Uses public third-party APIs and open-weight local models. | **Info** |

---

## 4. RAG Quality & Ingestion Pipeline
* **Chunking Strategy:** Structured Markdown splitting by header section (`app/rag/chunker.py`) with metadata tagging (`model`, `section`, `category`, `source_file`).
* **Chunk Size:** Average chunk size ~180-350 tokens, focused on single technical specifications or policies.
* **Retrieval Method:** Hybrid retrieval combining BM25 keyword matching with TF-IDF cosine similarity vector reranking (`app/rag/hybrid.py:40-95`).
* **RAG Limitations:**
  1. No persistent vector database (e.g. ChromaDB, Qdrant); index is rebuilt or loaded in-memory from JSON on startup.
  2. TF-IDF vector space vocabulary is computed at runtime and lacks semantic synonym expansion for unstemmed multilingual terms.
"""

with open(os.path.join(audit_dir, "08_AI_REPORT.md"), "w") as fp:
    fp.write(ai_content.strip() + "\n")
print("08_AI_REPORT.md created.")

# -------------------------------------------------------------
# 02_FINDINGS.md
# -------------------------------------------------------------
findings_content = """# 02_FINDINGS.md - Comprehensive Technical Findings Register

| ID | Category | Severity | Location | Evidence | Impact | Recommended Fix | Effort | Confidence | OWASP/CWE Ref |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Security | **CRITICAL** | `app/api/routes.py:389-392, 423-426` | `if requested and (requested.startswith("test_") or requested.startswith("user_")...): sender_id = requested` | Broken Object Level Authorization (IDOR). Any unauthenticated user can read/export chat history of any user ID starting with `user_`. | Remove arbitrary user prefix bypass; strictly enforce verified session cookie or admin token. | S | High | CWE-284, CWE-639 |
| **SEC-02** | Security | **HIGH** | `app/api/routes.py:37-41` | `return xff.split(",")[0].strip()` | IP Lockout & Rate-Limit Spoofing. Attacker can supply spoofed `X-Forwarded-For` header to evade lockout on `/admin/unlock` and admin endpoints. | Use `request.remote_addr` sanitized by `ProxyFix` rather than raw `X-Forwarded-For`. | S | High | CWE-290, CWE-345 |
| **SEC-03** | Security | **HIGH** | `app/config.py:50-53` | `ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "kepler_admin_secret_key_2026")` | Hardcoded default secrets for Admin Key and PII encryption key. If env vars are absent, production boots with known keys. | Fail closed in production (`validate_config()`) if default fallback secrets are detected. | S | High | CWE-798, CWE-1188 |
| **SEC-04** | Security | **MEDIUM** | `app/utils/crypto.py:46-48` | `except Exception as e: return plaintext` | Fail-open encryption fallback. If AES-GCM encryption errors, customer PII/chat text is saved in plaintext without raising an alert. | Raise an exception or abort write when encryption fails to prevent silent plaintext storage. | S | High | CWE-311, CWE-209 |
| **AI-01** | AI-LLM | **HIGH** | `app/agent/llm.py:25` | `quote the exact figures... (e.g. 4,385.00 AED for CX-02, 490.00 AED for 4x6 media...)` | Direct breach of Hard Rule 1 & Hard Rule 4. Hardcoded prices in system prompt contradict live database on price updates. | Remove all hardcoded prices from `SYSTEM_PROMPT`; inject verified pricing strictly from `structured_facts`. | S | High | Hard Rule 1, 4 |
| **AI-02** | AI-LLM | **MEDIUM** | `app/cognitive/understander.py:517` | `if rule_res.intent.confidence >= 0.85 and rule_res.intent.primary_intent != "unknown": return rule_res` | General catch-all intent `rag` was assigned confidence `1.0`, bypassing AI NLU extraction for conversational greetings/introductions. | Assign lower confidence (0.6) to `rag` catch-all or allow LLM refinement when primary intent is generic. | S | High | Reliability |
| **ARCH-01** | Architecture | **HIGH** | `app/agent/pipeline.py:1-2245` | Monolithic God-Class spanning 2,245 lines with 20+ functional branches | Severe architectural coupling and technical debt. Violates single responsibility principle; maintenance hazard. | Refactor into dedicated domain intent handlers (PricingHandler, QuoteHandler, LeadHandler, SpecsHandler). | L | High | Technical Debt |
| **PERF-01** | Performance | **HIGH** | `app/agent/llm.py:49, 72` | `requests.post(url, json=payload, timeout=15.0)` | Synchronous blocking HTTP I/O in Gunicorn worker threads. Two concurrent slow LLM calls exhaust all 2 worker processes. | Offload slow generation to asynchronous task queue (Celery/RQ) or use streaming SSE. | M | High | CWE-400 |
| **PERF-02** | Performance | **MEDIUM** | `app/storage/messages.py:32, 74` | `cur.execute("PRAGMA table_info(messages)")` | Unnecessary database introspection. Table metadata is queried on every message write and read turn. | Cache table column names in memory at application startup. | S | High | Performance |
| **DATA-01** | Backend | **MEDIUM** | `app/cognitive/state_machine.py:208-210` | `if existing: state.version = existing["version"]; continue` | Lost Update race condition. On version collision, optimistic locking reloads version and overwrites concurrent state. | Perform field-level three-way merge or use database row-level locking (`BEGIN IMMEDIATE`). | M | High | Concurrency |
| **OPS-01** | DevOps | **MEDIUM** | `Dockerfile:1-25` | `RUN pip install -r requirements.txt` | Unpinned build dependency installation. `requirements.txt` has loose ranges (`Flask>=3.0.0`) instead of `requirements.lock`. | Use `pip install --no-deps -r requirements.lock` in Dockerfile for reproducible container builds. | S | High | DevOps |
| **OPS-02** | DevOps | **LOW** | `app/main.py:12-30` | Missing HTTP security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) | Security headers rely solely on external reverse proxy. Standalone or direct container deployment is vulnerable to clickjacking. | Add Flask `@app.after_request` hook applying standard security headers. | S | High | OWASP A05:2021 |
"""

with open(os.path.join(audit_dir, "02_FINDINGS.md"), "w") as fp:
    fp.write(findings_content.strip() + "\n")
print("02_FINDINGS.md created.")

# -------------------------------------------------------------
# 04_SUMMARY.md
# -------------------------------------------------------------
summary_content = """# 04_SUMMARY.md - Executive Summary & System Health Scorecard

## Executive Summary
An exhaustive, evidence-based technical and architectural audit of the **Kepler Tech CX-02 Sales AI** repository was conducted. The codebase contains **220 non-excluded files**, **19,403 lines of Python code**, and a comprehensive test suite of **231 automated tests** currently passing at 100%.

The system possesses a sophisticated and disciplined dual-track design: commercial authority is strictly gated away from LLM hallucination via deterministic tools and claim validators. However, critical vulnerabilities exist in access control (IDOR on conversation history), header spoofing on IP lockouts, hardcoded default secrets, and a monolithic 2,245-line agent pipeline.

---

## System Health Scorecard (1 to 10)

| Dimension | Score | Justification & Benchmark |
| :--- | :---: | :--- |
| **Architecture** | **6.5 / 10** | Strong dual-track concept and clean cognitive separation (Reader, Understander, Thinker, Composer), but dragged down by the massive monolithic `app/agent/pipeline.py` (2,245 lines) acting as a God-object. |
| **Backend & Runtime** | **6.0 / 10** | Robust SQLite WAL mode and busy timeout handling, but plagued by synchronous blocking LLM I/O in worker processes, lack of connection pooling, and metadata introspection queries on every turn. |
| **AI Safety & Grounding**| **8.5 / 10** | Outstanding commercial grounding enforcement. Pre-guardrails, claim-by-claim numerical validators, and deterministic circuit breakers provide superior defense against hallucinations. Knocked down by hardcoded prices inside the LLM system prompt. |
| **Security & Privacy** | **5.5 / 10** | High severity IDOR on `/history` and `/history/export` (`?sender_id=user_...`), raw `X-Forwarded-For` parsing evading lockout, hardcoded fallback encryption keys, and silent fail-open encryption. |
| **Code Quality** | **7.0 / 10** | Clean naming conventions, consistent docstrings, and comprehensive typing across cognitive modules, but high cyclomatic complexity in router and pipeline branches. |
| **Performance & Scale** | **6.0 / 10** | Fast in-memory BM25 retrieval (~5ms), but synchronous 15s LLM calls create concurrency bottlenecks under Gunicorn multi-worker deployments. |
| **Testing & Verification**| **9.0 / 10** | Exceptional test suite: 231 tests covering security, guardrails, state machine, normalizer, and edge cases, paired with a 300-item golden evaluation benchmark. |
| **DevOps & Operations** | **7.0 / 10** | Working Dockerfile, docker-compose, and GitHub Actions CI. Needs strict lockfile builds in Docker and automated DB backup verification. |
| **OVERALL SCORE** | **6.9 / 10** | **Production-Capable with Critical Vulnerabilities Requiring Immediate Remediation.** |

---

## Top 10 Priority Remediation Actions
1. **Fix IDOR in `/history` and `/history/export` (SEC-01):** Restrict access strictly to authenticated admin tokens or the verified signed session cookie.
2. **Patch IP Lockout Bypass (SEC-02):** Replace raw `X-Forwarded-For` parsing with sanitized `request.remote_addr`.
3. **Eliminate Hardcoded Secrets (SEC-03):** Enforce fail-closed validation in `validate_config()` for `ADMIN_API_KEY` and `PII_ENCRYPTION_KEY`.
4. **Remove Hardcoded Prices in LLM Prompt (AI-01):** Strip hardcoded prices from `app/agent/llm.py:25` to prevent catalog contradiction.
5. **Fail-Closed on Encryption Errors (SEC-04):** Abort write and raise error rather than storing unencrypted plaintext in `app/utils/crypto.py`.
6. **Eliminate Per-Turn Table Introspection (PERF-02):** Cache table columns at startup instead of running `PRAGMA table_info` on every message.
7. **Fix Optimistic Locking Lost Update (DATA-01):** Implement field-level merging on version collisions in `app/cognitive/state_machine.py`.
8. **Enforce Lockfile in Dockerfile (OPS-01):** Install from `requirements.lock` to ensure reproducible builds.
9. **Inject Security Headers in Flask (OPS-02):** Register global `@app.after_request` handler applying CSP, X-Frame-Options, and HSTS.
10. **Decompose Monolithic Pipeline (ARCH-01):** Break `app/agent/pipeline.py` into distinct modular domain handlers.
"""

with open(os.path.join(audit_dir, "04_SUMMARY.md"), "w") as fp:
    fp.write(summary_content.strip() + "\n")
print("04_SUMMARY.md created.")

# -------------------------------------------------------------
# 05_ROADMAP.md
# -------------------------------------------------------------
roadmap_content = """# 05_ROADMAP.md - Strategic Remediation Roadmap

```mermaid
graph TD
    Phase1[Phase 1: Quick Wins < 1 Day] --> Phase2[Phase 2: Short-Term 1-2 Weeks]
    Phase2 --> Phase3[Phase 3: Long-Term Architecture]
    
    subgraph "Phase 1: Security & Prompt Integrity"
        SEC01[Fix History IDOR]
        SEC02[Fix IP Spoofing]
        SEC03[Enforce Strict Env Secrets]
        AI01[Strip Hardcoded Prices from Prompt]
        PERF02[Cache Table Columns]
    end

    subgraph "Phase 2: Reliability & Concurrency"
        SEC04[Fail-Closed Encryption]
        DATA01[Resolve Optimistic Lost Updates]
        OPS01[Lockfile in Dockerfile]
        OPS02[Security Headers Middleware]
    end

    subgraph "Phase 3: Scalability & Modularity"
        ARCH01[Decompose pipeline.py]
        PERF01[Async LLM Generation Queue]
    end

    Phase1 --> SEC01
    Phase1 --> SEC02
    Phase1 --> SEC03
    Phase1 --> AI01
    Phase1 --> PERF02
    
    Phase2 --> SEC04
    Phase2 --> DATA01
    Phase2 --> OPS01
    Phase2 --> OPS02
    
    Phase3 --> ARCH01
    Phase3 --> PERF01
```

---

## Phase 1: Quick Wins (< 1 Day Effort)
* [ ] **SEC-01: Remove unverified `sender_id` bypass in `/history` and `/history/export`.**
  * *Files:* `app/api/routes.py:389-400, 423-432`
  * *Action:* Only allow `sender_id` parameter override when `is_admin == True`.
* [ ] **SEC-02: Sanitize IP extraction in `get_client_ip()`.**
  * *Files:* `app/api/routes.py:37-41`
  * *Action:* Use `request.remote_addr` (properly populated by `ProxyFix`).
* [ ] **SEC-03: Enforce fail-closed startup configuration.**
  * *Files:* `app/config.py:validate_config()`
  * *Action:* Prevent boot if `ADMIN_API_KEY` or `PII_ENCRYPTION_KEY` match default fallback constants in production.
* [ ] **AI-01: Remove hardcoded commercial prices from LLM System Prompt.**
  * *Files:* `app/agent/llm.py:25`
  * *Action:* Keep prompt generic; rely strictly on `structured_facts` payload.
* [ ] **PERF-02: Remove per-turn `PRAGMA table_info` queries.**
  * *Files:* `app/storage/messages.py:32, 74`
  * *Action:* Store known table schema columns in a module constant.

---

## Phase 2: Short-Term Hardening (1–2 Weeks Effort)
* [ ] **SEC-04: Fail-closed field encryption.**
  * *Files:* `app/utils/crypto.py:46-48`
  * *Action:* Throw `CryptoError` on encryption failure rather than returning plaintext.
* [ ] **DATA-01: Fix Lost Update in `conversation_states`.**
  * *Files:* `app/cognitive/state_machine.py:205-210`
  * *Action:* Implement selective slot merging on version collisions before retrying.
* [ ] **OPS-01: Pin Docker dependencies to lockfile.**
  * *Files:* `Dockerfile`
  * *Action:* Update container build to run `pip install -r requirements.lock`.
* [ ] **OPS-02: Register HTTP Security Headers.**
  * *Files:* `app/main.py`
  * *Action:* Add `@app.after_request` adding `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Content-Security-Policy`.

---

## Phase 3: Long-Term Architectural Evolution (> 2 Weeks Effort)
* [ ] **ARCH-01: Decompose `app/agent/pipeline.py` Monolith.**
  * *Action:* Refactor into modular pipeline handlers:
    * `app/agent/handlers/pricing_handler.py`
    * `app/agent/handlers/technical_rag_handler.py`
    * `app/agent/handlers/lead_capture_handler.py`
    * `app/agent/handlers/handoff_handler.py`
* [ ] **PERF-01: Asynchronous Non-Blocking LLM Dispatch.**
  * *Action:* Transition LLM calling to an asynchronous queue (Celery or background worker) or native SSE streaming to avoid starving Gunicorn WSGI threads.
"""

with open(os.path.join(audit_dir, "05_ROADMAP.md"), "w") as fp:
    fp.write(roadmap_content.strip() + "\n")
print("05_ROADMAP.md created.")

# -------------------------------------------------------------
# 06_UNVERIFIED.md
# -------------------------------------------------------------
unverified_content = """# 06_UNVERIFIED.md - Unverified Items & External Environmental Dependencies

In accordance with Audit Rule 2 (*EVIDENCE OR NOTHING*), the following items could not be 100% verified via automated local execution due to external service credentials, production network requirements, or live third-party dependencies.

| Item ID | Component | Claim / Behavior Under Review | Reason Unverified Locally | Action Required from User / Operator to Verify |
| :--- | :--- | :--- | :--- | :--- |
| **UNV-01** | WhatsApp Cloud API | Real-time outbound delivery of messages via Meta Graph API (`app/whatsapp/client.py:send_whatsapp_message`). | No live Meta `WHATSAPP_TOKEN` or test phone number configured in local `.env`. | Provide test WhatsApp Cloud API credentials to verify real webhook handoff and outbound payload receipt. |
| **UNV-02** | OpenRouter Live Model | Response latency, rate limits, and actual output token structure from `meta-llama/llama-3.3-70b-instruct`. | `OPENROUTER_API_KEY` is not populated; system gracefully fell back to local Ollama `qwen2.5:7b`. | Provide OpenRouter sandbox API key to test live provider latency and streaming compatibility. |
| **UNV-03** | Nginx Edge Rate Limiting | Burst connection rejection (HTTP 429) at 20 req/s defined in `scripts/nginx.conf`. | Local dev environment executes against Gunicorn directly; Nginx reverse proxy daemon is not running locally. | Deploy test container behind active Nginx instance and run ApacheBench / wrk load test. |
| **UNV-04** | Offbox S3/Rsync Backup | Off-box automated database backup replication (`scripts/offbox_backup_copy.py`). | External offsite storage credentials (`OFFBOX_BACKUP_DEST`) not configured in development environment. | Run backup script in staging environment with verified remote storage destination. |
"""

with open(os.path.join(audit_dir, "06_UNVERIFIED.md"), "w") as fp:
    fp.write(unverified_content.strip() + "\n")
print("06_UNVERIFIED.md created.")
