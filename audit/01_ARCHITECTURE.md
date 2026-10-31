# 01_ARCHITECTURE.md - System Architecture & Structural Analysis

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
