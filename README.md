# cx02-sales-ai

A production-grade, strictly bounded RAG and tool-calling sales assistant for the **Citizen CX-02 dye-sublimation photo printer**, distributed by **Kepler Tech LLC (Dubai)**.

Supports **REST HTTP API** and **WhatsApp Cloud API**, operating in AED currency with deterministic tool arithmetic, strict input/output guardrails, and full offline extractive fallback resilience.

---

## 1. Product Scope & Catalog

Strictly scoped to the Citizen CX-02 and its official whitelisted accessories:
* **Citizen CX-02 Photo Printer (`CX-02`)**: 4,385.00 AED (old: 4,900.00 AED)
* **Citizen 4x6" Media Set (`CX2-MS46-2PC`)**: 490.00 AED (old: 500.00 AED) — estimated 800 prints/box
* **Citizen 5x7" Media Set (`CX2-MS57-2PC`)**: 500.00 AED (old: 550.00 AED) — verified 460 prints/box
* **Citizen 6x8" Media Set (`CX2-MS68-2PC`)**: 500.00 AED (old: 550.00 AED) — estimated 400 prints/box
* **Citizen CX-02 Carry Bag (`CX-02-BAG`)**: 325.00 AED (old: 340.00 AED)
* **Citizen Thermal Head Cleaning Pen (`CITIZEN-PEN`)**: 190.00 AED

All other Citizen models (`CX-02W`, `CX-02S`, `CY-02`, `CZ-01`) and competitor brands (`DNP`, `Fuji`, `HiTi`, `Sinfonia`, `Mitsubishi`, `Epson`, `Canon`) are refused politely with an automatic human handoff.

---

## 2. Hard Operational Rules

1. **Zero Invented Prices or Commercial Terms**: All numbers originate in code reading `data/products.json` and `data/policies.json`.
2. **Context-Only Grounding**: Technical questions are phrased solely from retrieved chunks. Unverified queries reply with a polite handoff.
3. **Strict Output Validator**: Scans all responses for ungrounded numbers, prices, or commercial claims, replacing violations with an extractive context excerpt.
4. **Unknown Policies Hand Off**: Unverified policies in `data/policies.json` default to `null` and trigger an immediate handoff.
5. **Conditional VAT**: Quotations omit VAT unless `VAT_RATE` and `PRICES_INCLUDE_VAT` are explicitly configured.
6. **Price Freshness**: Prices carry an `as_of` date. If older than 14 days, a confirmation note is automatically appended.

---

## 3. Quick Start & Setup

### Local Setup
```bash
# 1. Clone & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Ingest knowledge base chunks
python app/rag/chunker.py

# 4. Start the server
python app/main.py
```

### Docker Deployment
```bash
# Build and run with Docker Compose
docker compose up -d --build
```

---

## 4. Verification & Testing

### Running Unit Tests (47 tests)
```bash
venv/bin/pytest tests/ -v
```

### Running the 220-Item Evaluation Benchmark
```bash
venv/bin/python eval/run_eval.py
```

**Benchmark Results**:
* 🛡️ **Guardrail Accuracy**: 100.00% (75/75)
* 🔧 **Tool Accuracy**: 100.00% (65/65)
* 📚 **Knowledge RAG**: 100.00% (50/50)
* ⚡ **Hybrid (R+T)**: 100.00% (30/30)
* 🏷️ **Hallucinated Prices**: Exactly 0
* ⏱️ **Median Latency**: 0.013s

---

## 5. API Reference

### `POST /chat`
Send a customer query:
```json
{
  "message": "What is the price of the Citizen CX-02 printer?",
  "phone": "+971501234567"
}
```

### `GET /health`
Inspect service health and catalog readiness.

### `GET/POST /webhook`
Meta WhatsApp Cloud API webhook with HMAC-SHA256 signature verification and message deduplication.

### `POST /quote`
Direct quotation endpoint generating verified arithmetic with quantity caps (1–1000).

### `GET /leads`
Extract captured customer leads for CRM ingestion.
