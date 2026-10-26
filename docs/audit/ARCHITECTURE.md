# Architecture Documentation — Citizen CX-02 Sales AI

**Document Version**: 1.0 (Audit Snapshot)  
**Date**: 2026-10-26  
**Auditor**: Principal Engineer (Independent Technical Audit)  
**Target Repository**: `cx02-sales-ai` (Kepler Tech LLC, Dubai)

---

## 1. System Context

The Citizen CX-02 Sales AI is a specialized sales and customer-inquiry assistant built specifically for Kepler Tech LLC (Dubai). Its purpose is to handle customer interactions for exactly ONE primary product—the **Citizen CX-02 dye-sublimation photo printer**—and its five whitelisted official accessories.

```mermaid
flowchart TD
    subgraph Clients["Customer Ingress Channels"]
        WebUser["Web Browser / Test Console"]
        WhatsAppUser["WhatsApp Mobile User"]
    end

    subgraph External["External Gateways & Services"]
        MetaGraph["Meta WhatsApp Cloud API"]
        OllamaEngine["Local Ollama Daemon (Port 11434)"]
        KeplerSalesDesk["Kepler Tech Human Sales Desk\n(Phone: 00971 4 323 1008)"]
    end

    subgraph AppServer["Flask Application Core (Port 5000)"]
        Routes["Blueprint Routes\n(app/api/routes.py)"]
        Pipeline["CX02Pipeline\n(app/agent/pipeline.py)"]
        Router["Rule-Based Intent Router\n(app/agent/router.py)"]
        Guardrails["Pre & Post Guardrails\n(app/agent/guardrails.py)"]
        RAGModule["BM25 Retriever & Chunk Model\n(app/rag/retriever.py)"]
        LLMModule["LLM Client & Validator (Dead Code)\n(app/agent/llm.py)"]
        Tools["Deterministic Commercial Tools\n(app/tools/*.py)"]
    end

    subgraph Storage["Persistent Storage"]
        SQLiteDB[("SQLite Database\ndata/sales_ai.db")]
        JSONData["JSON Catalog & Policies\n(data/products.json, data/policies.json)"]
        AuditLog["JSONL Audit Log (Stale)\n(data/audit.jsonl)"]
    end

    WebUser -->|HTTP POST /chat| Routes
    WhatsAppUser -->|Message| MetaGraph
    MetaGraph -->|Webhook POST /webhook| Routes
    Routes --> Pipeline
    Pipeline --> Guardrails
    Pipeline --> Router
    Pipeline --> Tools
    Pipeline --> RAGModule
    Pipeline -.->|Unused / Dead Code| LLMModule
    LLMModule -.->|HTTP POST /api/chat| OllamaEngine
    Tools --> JSONData
    Pipeline --> SQLiteDB
    Tools --> SQLiteDB
    Pipeline -->|Handoff Record| KeplerSalesDesk
```

---

## 2. Component Inventory & Code Map

| Component / Subsystem | Primary File Path | Line Range | Responsibilities |
| :--- | :--- | :--- | :--- |
| **Application Entry Point** | `app/main.py` | L1–L26 | Initializes Flask WSGI application, binds Blueprint, runs dev server |
| **Configuration** | `app/config.py` | L1–L46 | Loads `.env`, exposes paths, VAT settings, contact info, model params |
| **HTTP Blueprint Routes** | `app/api/routes.py` | L1–L156 | Exposes `/`, `/health`, `/chat`, `/quote`, `/leads`, `/webhook` |
| **Pipeline Core** | `app/agent/pipeline.py` | L1–L342 | Coordinates history, intent routing, tool invocation, RAG, logging |
| **Intent Router** | `app/agent/router.py` | L1–L245 | 14-level priority regex keyword classifier |
| **Input & Output Guardrails** | `app/agent/guardrails.py` | L1–L148 | Rejects competitors, other Citizen models, abuse, injection, A4 |
| **Output Validator** | `app/agent/validator.py` | L1–L118 | Verifies grounding of numbers, prices, commercial claims; extractive fallback |
| **LLM Interface** | `app/agent/llm.py` | L1–L77 | Ollama HTTP client (`/api/chat`). **Note: Dead code in CX02Pipeline** |
| **Orchestrator Wrapper** | `app/agent/orchestrator.py` | L1–L9 | Facade wrapper delegating to `CX02Pipeline` |
| **BM25 Retriever** | `app/rag/retriever.py` | L1–L125 | Loads `chunks.json`, runs BM25Okapi search with score and coverage gating |
| **Chunk Ingestion** | `app/rag/ingest.py` | L1–L80 | Parses `data/kb/*.md` into structured JSON chunks |
| **Pricing & Stock Tool** | `app/tools/pricing.py` | L1–L212 | Reads `products.json`, computes cost/print, enforces price freshness |
| **Quotation Tool** | `app/tools/quote.py` | L1–L137 | Validates 1–1000 bounds, calculates subtotals/VAT, stores quote in DB |
| **Policy Tool** | `app/tools/policies.py` | L1–L61 | Reads `policies.json`; handles unknown policies with handoff |
| **Handoff & Lead Tool** | `app/tools/handoff.py` | L1–L60 | Records human escalation records and sales lead records in DB |
| **Product Link Tool** | `app/tools/links.py` | L1–L24 | Resolves official Kepler Tech URLs for whitelisted SKUs |
| **SQLite Storage Layer** | `app/storage/db.py` | L1–L88 | Manages SQLite connection, auto-migrates missing columns |
| **Message & Lead Storage** | `app/storage/messages.py`, `leads.py` | — | Deduplication, conversation turns, lead state machine |
| **Audit Logger** | `app/audit_logging/audit.py` | L1–L42 | JSONL record writer. **Note: Never called in pipeline** |

---

## 3. Sequence Traces of Canonical Execution Routes

### 3.1 Route 1: Price Inquiry (`INTENT: price`, Priority 12)
```mermaid
sequenceDiagram
    autonumber
    actor User as Customer / Web Client
    participant App as app/api/routes.py
    participant Pipe as app/agent/pipeline.py
    participant Router as app/agent/router.py
    participant Tools as app/tools/pricing.py
    participant DB as app/storage/messages.py

    User->>App: POST /chat {"message": "How much is the Citizen CX-02 photo printer?"}
    App->>Pipe: process(user_message, sender_id, channel)
    Pipe->>Router: classify_intent(user_msg)
    Router-->>Pipe: {"intent": "price", "priority": 12}
    Pipe->>Pipe: determine_target_sku(user_msg) -> "CX-02"
    Pipe->>Tools: get_price("CX-02")
    Tools-->>Pipe: {"status": "success", "price": 4385.00, "formatted_price": "4,385.00 AED", ...}
    Pipe->>Pipe: Render deterministic pricing template
    Pipe->>DB: log_message(role="user"), log_message(role="assistant")
    Pipe-->>App: {"reply": "The official price for...", "intent": "price", ...}
    App-->>User: 200 OK JSON
```

### 3.2 Route 2: Technical Knowledge / Datasheet (`INTENT: rag`, Priority 14)
```mermaid
sequenceDiagram
    autonumber
    actor User as Customer
    participant Pipe as app/agent/pipeline.py
    participant Router as app/agent/router.py
    participant RAG as app/rag/retriever.py
    participant DB as app/storage/messages.py

    User->>Pipe: process("What is the print method of the CX-02?")
    Pipe->>Router: classify_intent(user_msg)
    Router-->>Pipe: {"intent": "rag", "priority": 14}
    Pipe->>RAG: retrieve("What is the print method of the CX-02?", top_k=2)
    RAG-->>Pipe: [Chunk(section="Print Engine", text="...")]
    Pipe->>Pipe: Extract top 5 non-header lines directly from chunk
    Pipe->>DB: log_message(user), log_message(assistant)
    Pipe-->>User: {"reply": "Here are the official specifications...", "chunks": 2}
```

### 3.3 Route 3: Hybrid Quotation & Specs (`INTENT: datasheet`, Priority 5)
```mermaid
sequenceDiagram
    autonumber
    actor User as Customer
    participant Pipe as app/agent/pipeline.py
    participant Router as app/agent/router.py
    participant Quote as app/tools/quote.py
    participant RAG as app/rag/retriever.py

    User->>Pipe: process("Can you quote me 2 CX-02 printers and tell me their dimensions?")
    Pipe->>Router: classify_intent()
    Note over Router: Matched 'dimensions' in DATASHEET_KEYWORDS
    Router-->>Pipe: {"intent": "datasheet", "priority": 5}
    Note over Pipe: has_price_terms=True ("quote") & has_knowledge_terms=True ("dimensions")
    Pipe->>Quote: create_quote(items=[{"sku": "CX-02", "qty": 2}])
    Quote-->>Pipe: {"status": "success", "subtotal": 8770.00, "text_summary": "📄 Official Quotation..."}
    Pipe->>RAG: retrieve("...", top_k=2)
    RAG-->>Pipe: [Chunk(section="Dimensions & Weight")]
    Pipe->>Pipe: Assemble combined response (Extracted Specs + Quote Text)
    Pipe-->>User: {"reply": "Specifications... \n\n📄 Official Quotation..."}
```

### 3.4 Route 4: Unknown Policy Handoff (`INTENT: policies`, Priority 6)
```mermaid
sequenceDiagram
    autonumber
    actor User as Customer
    participant Pipe as app/agent/pipeline.py
    participant Router as app/agent/router.py
    participant Pol as app/tools/policies.py
    participant Handoff as app/tools/handoff.py
    participant DB as app/storage/handoffs.py

    User->>Pipe: process("What are your delivery charges to Sharjah?")
    Pipe->>Router: classify_intent()
    Router-->>Pipe: {"intent": "policies", "priority": 6, "policy_name": "delivery charges"}
    Pipe->>Pol: get_policy("delivery charges")
    Note over Pol: data/policies.json has delivery_charges: null
    Pol-->>Pipe: {"status": "unknown", "handoff": true, "message": "Official terms require confirmation..."}
    Pipe->>Handoff: handoff_to_human(reason="Policy inquiry...")
    Handoff->>DB: save_handoff()
    Pipe-->>User: {"reply": "Official terms require confirmation... Contact 00971 4 323 1008"}
```

### 3.5 Route 5: Scope & Guardrail Block (`INTENT: guardrails`, Priority 1)
```mermaid
sequenceDiagram
    autonumber
    actor User as Adversary / Customer
    participant Pipe as app/agent/pipeline.py
    participant Guard as app/agent/guardrails.py
    participant Handoff as app/tools/handoff.py

    User->>Pipe: process("Do you have the DNP DS620 photo printer?")
    Pipe->>Guard: check_pre_guardrails("... dnp ds620 ...")
    Guard-->>Pipe: is_safe=False, type="competitor", details={"response": "We do not provide comparisons..."}
    Pipe->>Handoff: handoff_to_human(reason="Competitor brand 'dnp'")
    Pipe-->>User: {"reply": "I specialize exclusively in the Citizen CX-02... \n\nI have routed your inquiry..."}
```

---

## 4. SQLite Data Model

The application uses a local SQLite database (`data/sales_ai.db`). Tables and schemas verified in `app/storage/db.py:L14-L64`:

```mermaid
erDiagram
    SESSIONS ||--o{ MESSAGES : "contains"
    SESSIONS {
        TEXT phone PK
        TIMESTAMP created_at
        TIMESTAMP last_activity
        TEXT quote_state
    }
    MESSAGES {
        INTEGER id PK
        TEXT phone
        TEXT role
        TEXT content
        TIMESTAMP timestamp
        TEXT sender_id
        TEXT message_id
        TEXT channel
    }
    LEADS {
        INTEGER id PK
        TEXT sender_id
        TEXT name
        TEXT phone
        TEXT email
        TEXT notes
        TEXT status
        TIMESTAMP created_at
    }
    QUOTES {
        INTEGER id PK
        TEXT quote_id UK
        TEXT sender_id
        TEXT customer_name
        TEXT phone
        TEXT items_json
        REAL subtotal
        REAL vat_amount
        REAL total
        TIMESTAMP created_at
    }
    HANDOFFS {
        INTEGER id PK
        TEXT sender_id
        TEXT reason
        TEXT summary
        TEXT phone
        TEXT status
        TIMESTAMP created_at
    }
    PENDING_LEADS {
        TEXT sender_id PK
        TEXT stage
        TEXT temp_name
        TEXT temp_phone
        TEXT last_intent
        TIMESTAMP updated_at
    }
```

---

## 5. Configuration & Environment Variables

| Variable Name | Type | Default Value | Source Code Location | Description & Security Note |
| :--- | :--- | :--- | :--- | :--- |
| `PORT` | `int` | `5000` | `app/config.py:L10` | Port for Flask web server |
| `DEBUG` | `bool` | `False` | `app/config.py:L11` | Flask debug mode flag |
| `SECRET_KEY` | `str` | `cx02-sales-secret-key-default` | `app/config.py:L12` | Session secret key (**Insecure default**) |
| `DATABASE_PATH` | `Path` | `data/sales_ai.db` | `app/config.py:L15` | Absolute or relative path to SQLite database |
| `PRICE_MAX_AGE_DAYS` | `int` | `14` | `app/config.py:L22` | Threshold for price freshness warning notice |
| `VAT_RATE` | `float` or `None` | `None` | `app/config.py:L26` | UAE VAT rate (e.g., `0.05`). None triggers safe fallback |
| `PRICES_INCLUDE_VAT` | `bool` or `None` | `None` | `app/config.py:L29` | Whether prices include VAT. None triggers safe fallback |
| `OLLAMA_BASE_URL` | `str` | `http://localhost:11434` | `app/config.py:L32` | Local Ollama API server endpoint |
| `OLLAMA_CHAT_MODEL` | `str` | `qwen2.5:7b` | `app/config.py:L33` | Ollama model tag (**Mismatch with local `qwen2.5:latest`**) |
| `OLLAMA_EMBED_MODEL` | `str` | `nomic-embed-text` | `app/config.py:L34` | Embedding model tag |
| `FORCE_EXTRACTIVE_MODE` | `bool` | `False` | `app/config.py:L35` | Forces bypass of Ollama LLM calling |
| `WHATSAPP_TOKEN` | `str` | `""` | `app/config.py:L38` | Meta Graph API bearer token (**Unused in code**) |
| `WHATSAPP_PHONE_NUMBER_ID` | `str` | `""` | `app/config.py:L39` | Meta WhatsApp business phone number ID |
| `WHATSAPP_VERIFY_TOKEN` | `str` | `cx02_sales_verify_token` | `app/config.py:L40` | Webhook verification token for Meta subscribe handshake |
| `WHATSAPP_APP_SECRET` | `str` | `""` | `app/config.py:L41` | Secret key for SHA-256 HMAC payload verification |

---

## 6. Trust Boundaries & Attack Surface

1. **Internet Ingress Boundary (Public Web)**:
   - Endpoint `/chat` accepts unauthenticated JSON payloads. No rate limiting or request throttling is applied.
   - Endpoint `/leads` allows unauthenticated `GET` requests, exposing all customer CRM records.
2. **Meta Cloud Webhook Boundary**:
   - Signature verification is bypassed if `WHATSAPP_APP_SECRET` is left empty.
   - Incoming messages are deduplicated using SQLite table lookup.
3. **LLM Engine Boundary**:
   - `app/agent/llm.py` connects to localhost Ollama. Currently inactive because `pipeline.py` uses direct string slicing.
4. **Data Storage Boundary**:
   - SQLite DB contains unencrypted names, phone numbers, and conversation logs.
