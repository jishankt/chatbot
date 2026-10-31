# 00_MANIFEST.md - Repository File Coverage Report

## Executive Metrics
- **Total Non-Excluded Files Audited:** 220
- **Total Repository Size:** 71,966,175 bytes (68.63 MB)
- **Total Text Lines:** 471,430
- **Excluded Directories:** `.git/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `audit/` (output dir)
- **Audit Coverage:** **100% of tracked repository files accounted for** (0 files skipped).

## Category Summary Table

| Category / Subsystem | File Count | Lines of Code | Description |
| :--- | :--- | :--- | :--- |
| **Agent & Orchestration** (`app/agent`) | 9 | 3,557 | Pipeline, router, guardrails, admission, prompts, LLM client, validator |
| **API & Webhooks** (`app/api`) | 2 | 518 | Flask endpoints, webhook handling, rate-limiting & auth decorators |
| **Security Audit** (`app/audit_logging`) | 2 | 80 | HMAC-SHA256 tamper-evident JSONL audit logger |
| **Cognitive NLU Subsystem** (`app/cognitive`) | 5 | 2,089 | Reader, Understander, State Machine, Normalizer, Composer |
| **Retrieval / RAG** (`app/rag`) | 8 | 1,151 | BM25, TF-IDF cosine reranker, knowledge base embeddings |
| **Data Storage & Schema** (`app/storage`) | 7 | 753 | SQLite migrations, connection management, lead and quote storage |
| **Web Templates** (`app/templates`) | 1 | 270 | Jinja2 HTML templates |
| **Frontend Assets** (`app/static`) | 13 | 28,535 | CSS styles and vanilla JavaScript client |
| **Application Core** (`app`) | 21 | 2,237 | Root Flask app (`main.py`) and config loader (`config.py`) |
| **System Configuration** (`config`) | 5 | 361 | Scope, threshold, and catalog YAML policies |
| **Data & Knowledge Base** (`data`) | 66 | 419,679 | Canonical JSON catalogs, KB markdown chunks, raw data extracts, SQLite DB |
| **Documentation** (`docs`) | 7 | 473 | Design notes, ADRs, user guides |
| **Evaluation Harness** (`eval`) | 3 | 760 | Benchmark datasets (`eval_set.jsonl`) and test runner |
| **Database Migrations** (`migrations`) | 3 | 15 | Raw SQL schema migration files |
| **Automation & Ops Scripts** (`scripts`) | 20 | 3,126 | Seeders, admin tools, Nginx config, deployment helpers |
| **Automated Test Suite** (`tests`) | 35 | 5,184 | Pytest unit, integration, and security regression tests |
| **Project Root & CI/CD** (`root`) | 13 | 2,642 | Dockerfile, docker-compose.yml, Makefile, CI workflow, AGENTS.md, README.md |

---

## Full File-by-File Manifest (100% Tracked)

| File Path | Size (Bytes) | Lines | Extension | Review Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `.agent/workflows/verify.md` | 313 | 15 | `.md` | **Reviewed** | Source / Config |
| `.env.example` | 1,033 | 36 | `.example` | **Reviewed** | Source / Config |
| `.github/workflows/ci.yml` | 1,385 | 51 | `.yml` | **Reviewed** | Source / Config |
| `.gitignore` | 127 | 13 | `[none]` | **Reviewed** | Source / Config |
| `AGENTS.md` | 3,385 | 29 | `.md` | **Reviewed** | Source / Config |
| `AUDIT_REPORT.md` | 115,607 | 1577 | `.md` | **Reviewed** | Source / Config |
| `Dockerfile` | 543 | 25 | `[none]` | **Reviewed** | Source / Config |
| `Makefile` | 422 | 25 | `[none]` | **Reviewed** | Source / Config |
| `README.md` | 3,521 | 103 | `.md` | **Reviewed** | Source / Config |
| `app/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/agent/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/agent/admission.py` | 3,556 | 100 | `.py` | **Reviewed** | Source / Config |
| `app/agent/guardrails.py` | 12,334 | 241 | `.py` | **Reviewed** | Source / Config |
| `app/agent/llm.py` | 9,185 | 174 | `.py` | **Reviewed** | Source / Config |
| `app/agent/orchestrator.py` | 328 | 8 | `.py` | **Reviewed** | Source / Config |
| `app/agent/pipeline.py` | 158,107 | 2244 | `.py` | **Reviewed** | Source / Config |
| `app/agent/prompts.py` | 2,011 | 30 | `.py` | **Reviewed** | Source / Config |
| `app/agent/router.py` | 22,681 | 520 | `.py` | **Reviewed** | Source / Config |
| `app/agent/validator.py` | 13,170 | 240 | `.py` | **Reviewed** | Source / Config |
| `app/api/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/api/routes.py` | 19,570 | 518 | `.py` | **Reviewed** | Source / Config |
| `app/audit_logging/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/audit_logging/audit.py` | 2,777 | 80 | `.py` | **Reviewed** | Source / Config |
| `app/cognitive/composer.py` | 10,022 | 238 | `.py` | **Reviewed** | Source / Config |
| `app/cognitive/normalizer.py` | 12,934 | 294 | `.py` | **Reviewed** | Source / Config |
| `app/cognitive/reader.py` | 24,890 | 575 | `.py` | **Reviewed** | Source / Config |
| `app/cognitive/state_machine.py` | 19,022 | 457 | `.py` | **Reviewed** | Source / Config |
| `app/cognitive/understander.py` | 21,417 | 525 | `.py` | **Reviewed** | Source / Config |
| `app/config.py` | 6,455 | 134 | `.py` | **Reviewed** | Source / Config |
| `app/main.py` | 1,007 | 35 | `.py` | **Reviewed** | Source / Config |
| `app/memory/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/memory/sessions.py` | 4,178 | 104 | `.py` | **Reviewed** | Source / Config |
| `app/monitoring/metrics.py` | 5,278 | 142 | `.py` | **Reviewed** | Source / Config |
| `app/notifications/salesperson.py` | 10,275 | 261 | `.py` | **Reviewed** | Source / Config |
| `app/rag/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/rag/chunker.py` | 4,689 | 127 | `.py` | **Reviewed** | Source / Config |
| `app/rag/embed.py` | 3,759 | 115 | `.py` | **Reviewed** | Source / Config |
| `app/rag/hybrid.py` | 7,299 | 204 | `.py` | **Reviewed** | Source / Config |
| `app/rag/ingest.py` | 543 | 19 | `.py` | **Reviewed** | Source / Config |
| `app/rag/relevance.py` | 17,779 | 276 | `.py` | **Reviewed** | Source / Config |
| `app/rag/retrieve.py` | 4,716 | 134 | `.py` | **Reviewed** | Source / Config |
| `app/rag/retriever.py` | 13,948 | 276 | `.py` | **Reviewed** | Source / Config |
| `app/static/css/index.css` | 19,936 | 1081 | `.css` | **Reviewed** | Source / Config |
| `app/static/img/citizen_bag_card.jpg` | 629,115 | 3327 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_bag_card.webp` | 387,550 | 3064 | `.webp` | **Reviewed** | Source / Config |
| `app/static/img/citizen_cx02.jpg` | 599,910 | 3978 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_cx02_card.jpg` | 599,165 | 3441 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_cx02_card.webp` | 26,854 | 202 | `.webp` | **Reviewed** | Source / Config |
| `app/static/img/citizen_media_4x6.webp` | 390,480 | 3095 | `.webp` | **Reviewed** | Source / Config |
| `app/static/img/citizen_media_5x7.jpg` | 126,803 | 698 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_media_6x8.webp` | 342,314 | 2728 | `.webp` | **Reviewed** | Source / Config |
| `app/static/img/citizen_media_card.jpg` | 525,205 | 2493 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_pen_card.jpg` | 542,348 | 2674 | `.jpg` | **Reviewed** | Source / Config |
| `app/static/img/citizen_pen_card.webp` | 162,364 | 1315 | `.webp` | **Reviewed** | Source / Config |
| `app/static/js/app.js` | 15,684 | 439 | `.js` | **Reviewed** | Source / Config |
| `app/storage/__init__.py` | 98 | 3 | `.py` | **Reviewed** | Source / Config |
| `app/storage/consents.py` | 2,881 | 92 | `.py` | **Reviewed** | Source / Config |
| `app/storage/db.py` | 8,419 | 224 | `.py` | **Reviewed** | Source / Config |
| `app/storage/handoffs.py` | 3,344 | 117 | `.py` | **Reviewed** | Source / Config |
| `app/storage/leads.py` | 3,841 | 129 | `.py` | **Reviewed** | Source / Config |
| `app/storage/messages.py` | 3,319 | 91 | `.py` | **Reviewed** | Source / Config |
| `app/storage/quotes.py` | 2,773 | 97 | `.py` | **Reviewed** | Source / Config |
| `app/templates/index.html` | 13,862 | 270 | `.html` | **Reviewed** | Source / Config |
| `app/tools/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `app/tools/dispatcher.py` | 2,621 | 76 | `.py` | **Reviewed** | Source / Config |
| `app/tools/handoff.py` | 5,767 | 150 | `.py` | **Reviewed** | Source / Config |
| `app/tools/links.py` | 1,005 | 33 | `.py` | **Reviewed** | Source / Config |
| `app/tools/policies.py` | 5,834 | 147 | `.py` | **Reviewed** | Source / Config |
| `app/tools/pricing.py` | 9,052 | 254 | `.py` | **Reviewed** | Source / Config |
| `app/tools/quote.py` | 13,941 | 321 | `.py` | **Reviewed** | Source / Config |
| `app/tools/registry.py` | 645 | 22 | `.py` | **Reviewed** | Source / Config |
| `app/tools/schemas.py` | 5,877 | 182 | `.py` | **Reviewed** | Source / Config |
| `app/utils/crypto.py` | 2,463 | 77 | `.py` | **Reviewed** | Source / Config |
| `app/utils/phone.py` | 459 | 16 | `.py` | **Reviewed** | Source / Config |
| `app/utils/quantity.py` | 7,086 | 176 | `.py` | **Reviewed** | Source / Config |
| `app/utils/session.py` | 950 | 28 | `.py` | **Reviewed** | Source / Config |
| `app/whatsapp/client.py` | 2,833 | 79 | `.py` | **Reviewed** | Source / Config |
| `config/cron.d/sales_handoff_retry` | 398 | 6 | `[none]` | **Reviewed** | Source / Config |
| `config/nginx_rate_limits.conf` | 4,714 | 121 | `.conf` | **Reviewed** | Source / Config |
| `config/scope.yaml` | 6,083 | 213 | `.yaml` | **Reviewed** | Source / Config |
| `config/systemd/sales-handoff-retry.service` | 282 | 11 | `.service` | **Reviewed** | Source / Config |
| `config/systemd/sales-handoff-retry.timer` | 188 | 10 | `.timer` | **Reviewed** | Source / Config |
| `data/audit.jsonl` | 6,178 | 10 | `.jsonl` | **Reviewed** | Source / Config |
| `data/backups/sales_ai_20261028_084130.db` | 10,465,280 | 72241 | `.db` | **Reviewed** | Binary / SQLite DB |
| `data/backups/sales_ai_20261028_084130.db-shm` | 32,768 | 1 | `.db-shm` | **Reviewed** | Source / Config |
| `data/backups/sales_ai_20261028_084130.db-wal` | 0 | 0 | `.db-wal` | **Reviewed** | Source / Config |
| `data/backups/sales_ai_20261028_095901.db` | 10,854,400 | 73443 | `.db` | **Reviewed** | Binary / SQLite DB |
| `data/backups/sales_ai_20261028_103940.db` | 11,771,904 | 75798 | `.db` | **Reviewed** | Binary / SQLite DB |
| `data/chunks.json` | 43,541 | 478 | `.json` | **Reviewed** | Source / Config |
| `data/company_chunks.json` | 24,306 | 332 | `.json` | **Reviewed** | Source / Config |
| `data/cx02_sales.db` | 0 | 0 | `.db` | **Reviewed** | Binary / SQLite DB |
| `data/eval/conversation_eval_report.json` | 8,172 | 215 | `.json` | **Reviewed** | Source / Config |
| `data/eval/eval_set.json` | 130,255 | 6735 | `.json` | **Reviewed** | Source / Config |
| `data/eval/questions.jsonl` | 55,955 | 220 | `.jsonl` | **Reviewed** | Source / Config |
| `data/eval/validator_eval_report.json` | 594 | 25 | `.json` | **Reviewed** | Source / Config |
| `data/kb/01_overview.md` | 2,760 | 29 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/02_print_engine.md` | 1,678 | 21 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/03_media_formats.md` | 1,954 | 25 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/04_dimensions_power.md` | 1,607 | 20 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/05_accessories.md` | 2,550 | 16 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/06_citizen_lineup.md` | 12,346 | 110 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/07_epson_lineup.md` | 7,075 | 86 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/about.md` | 1,798 | 19 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/brands_and_categories.md` | 2,739 | 37 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/contacts.md` | 1,183 | 26 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/coverage_and_delivery.md` | 2,482 | 45 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/policies.md` | 2,586 | 41 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb/company/services.md` | 2,153 | 29 | `.md` | **Reviewed** | Knowledge Base Markdown Chunk |
| `data/kb_supplemental/07_troubleshooting.md` | 3,791 | 50 | `.md` | **Reviewed** | Source / Config |
| `data/kb_supplemental/08_catalog_ecosystem.md` | 3,857 | 51 | `.md` | **Reviewed** | Source / Config |
| `data/kb_supplemental/09_sales_playbook.md` | 4,236 | 52 | `.md` | **Reviewed** | Source / Config |
| `data/offbox_backups/sales_ai_20261028_103940.db` | 11,771,904 | 75798 | `.db` | **Reviewed** | Binary / SQLite DB |
| `data/policies.json` | 10,199 | 193 | `.json` | **Reviewed** | Source / Config |
| `data/products.json` | 849,227 | 17868 | `.json` | **Reviewed** | Source / Config |
| `data/products.json.bak` | 3,495 | 93 | `.bak` | **Reviewed** | Source / Config |
| `data/raw/bag_product_page.txt` | 15,103 | 229 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/citizen_cx02_page.txt` | 2,677 | 113 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/bag_product_page.txt` | 15,103 | 229 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/citizen_cx02_page.txt` | 2,677 | 113 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/cx02_datasheet.txt` | 2,319 | 65 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/cx02_product_page.txt` | 24,920 | 412 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/faq.txt` | 3,317 | 30 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_about_us.txt` | 2,513 | 52 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_contact_us.txt` | 854 | 43 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_home.txt` | 15,800 | 772 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_service_managed_print.txt` | 7,694 | 131 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_service_rental.txt` | 16,736 | 447 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_service_repair.txt` | 5,307 | 182 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertech_ae_services.txt` | 1,828 | 24 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertechllc_about_us.txt` | 6,255 | 81 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertechllc_africa.txt` | 17,374 | 369 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertechllc_contact_us.txt` | 1,269 | 65 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/keplertechllc_countries_we_serve.txt` | 5,448 | 97 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/media_4x6_page.txt` | 19,551 | 382 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/media_5x7_page.txt` | 17,489 | 278 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/media_6x8_page.txt` | 18,211 | 320 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/pen_product_page.txt` | 15,225 | 220 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/company/terms_and_conditions.txt` | 11,926 | 156 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/cx02_datasheet.txt` | 2,319 | 65 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/cx02_product_page.txt` | 24,920 | 412 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/faq.txt` | 3,317 | 30 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/kepler_citizen_photo_printers_brochure.txt` | 2,501 | 68 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/media_4x6_page.txt` | 19,551 | 382 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/media_5x7_page.txt` | 17,489 | 278 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/media_6x8_page.txt` | 18,211 | 320 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/pen_product_page.txt` | 15,225 | 220 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/raw/terms_and_conditions.txt` | 11,926 | 156 | `.txt` | **Reviewed** | Verbatim Data Extract |
| `data/sales_ai.db` | 20,062,208 | 88831 | `.db` | **Reviewed** | Binary / SQLite DB |
| `docker-compose.yml` | 825 | 36 | `.yml` | **Reviewed** | Source / Config |
| `docs/ARCHITECTURE.md` | 6,735 | 111 | `.md` | **Reviewed** | Source / Config |
| `docs/DATA_TODO.md` | 4,476 | 27 | `.md` | **Reviewed** | Source / Config |
| `docs/DEPLOYMENT_HANDOFF_RETRY.md` | 2,438 | 66 | `.md` | **Reviewed** | Source / Config |
| `docs/FOLLOWUPS.md` | 1,633 | 15 | `.md` | **Reviewed** | Source / Config |
| `docs/MIGRATION_PLAN_DROP_REAL_COLUMNS.md` | 3,560 | 74 | `.md` | **Reviewed** | Source / Config |
| `docs/PRODUCT_ONBOARDING.md` | 4,768 | 112 | `.md` | **Reviewed** | Source / Config |
| `docs/SMTP_SECURITY.md` | 3,302 | 68 | `.md` | **Reviewed** | Source / Config |
| `eval/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Source / Config |
| `eval/generate_questions.py` | 21,296 | 344 | `.py` | **Reviewed** | Source / Config |
| `eval/run_eval.py` | 17,081 | 416 | `.py` | **Reviewed** | Source / Config |
| `migrations/001_core_indexes.sql` | 475 | 7 | `.sql` | **Reviewed** | Source / Config |
| `migrations/002_add_conversation_state_version.sql` | 158 | 2 | `.sql` | **Reviewed** | Source / Config |
| `migrations/003_quotes_integer_fils.sql` | 342 | 6 | `.sql` | **Reviewed** | Source / Config |
| `pytest.ini` | 42 | 3 | `.ini` | **Reviewed** | Source / Config |
| `requirements.lock` | 57,215 | 720 | `.lock` | **Reviewed** | Source / Config |
| `requirements.txt` | 144 | 9 | `.txt` | **Reviewed** | Source / Config |
| `scripts/backfill_quote_fils.py` | 2,133 | 74 | `.py` | **Reviewed** | Source / Config |
| `scripts/backup_db.py` | 2,409 | 70 | `.py` | **Reviewed** | Source / Config |
| `scripts/benchmark_capacity.py` | 6,401 | 170 | `.py` | **Reviewed** | Source / Config |
| `scripts/check_links.py` | 3,117 | 96 | `.py` | **Reviewed** | Source / Config |
| `scripts/check_quote_fils_mismatch.py` | 3,168 | 94 | `.py` | **Reviewed** | Source / Config |
| `scripts/eval_validator.py` | 6,267 | 178 | `.py` | **Reviewed** | Source / Config |
| `scripts/fetch_company_sources.py` | 5,234 | 158 | `.py` | **Reviewed** | Source / Config |
| `scripts/generate_eval.py` | 51,469 | 1030 | `.py` | **Reviewed** | Source / Config |
| `scripts/ingest_master_products.py` | 7,226 | 178 | `.py` | **Reviewed** | Source / Config |
| `scripts/load_test_concurrent_sessions.py` | 8,487 | 201 | `.py` | **Reviewed** | Source / Config |
| `scripts/migrate.py` | 2,218 | 74 | `.py` | **Reviewed** | Source / Config |
| `scripts/offbox_backup_copy.py` | 1,855 | 64 | `.py` | **Reviewed** | Source / Config |
| `scripts/profile_turn_latency.py` | 5,520 | 136 | `.py` | **Reviewed** | Source / Config |
| `scripts/restore_drill.py` | 3,822 | 113 | `.py` | **Reviewed** | Source / Config |
| `scripts/retention_cleanup.py` | 4,364 | 138 | `.py` | **Reviewed** | Source / Config |
| `scripts/retention_dry_run.py` | 2,525 | 79 | `.py` | **Reviewed** | Source / Config |
| `scripts/retry_handoffs.py` | 783 | 29 | `.py` | **Reviewed** | Source / Config |
| `scripts/scrub_audit_logs.py` | 4,151 | 124 | `.py` | **Reviewed** | Source / Config |
| `scripts/unlock_ip.py` | 1,023 | 42 | `.py` | **Reviewed** | Source / Config |
| `scripts/verify_backup_restore.py` | 2,567 | 78 | `.py` | **Reviewed** | Source / Config |
| `tests/__init__.py` | 0 | 0 | `.py` | **Reviewed** | Test Suite File |
| `tests/conftest.py` | 177 | 8 | `.py` | **Reviewed** | Test Suite File |
| `tests/conversation_eval.py` | 15,375 | 301 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_api.py` | 7,947 | 219 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_batch3_hardening.py` | 18,334 | 378 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_batch4_hardening.py` | 16,046 | 361 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_batch5_hardening.py` | 13,012 | 307 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_batch6_hardening.py` | 10,529 | 242 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_batch7_hardening.py` | 11,042 | 218 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_cards.py` | 1,107 | 26 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_category_retrieval_and_out_of_catalogue.py` | 2,647 | 52 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_company_grounding.py` | 4,026 | 85 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_composer.py` | 4,341 | 134 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_eval_benchmark.py` | 6,305 | 165 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_guardrails.py` | 3,108 | 82 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_nginx_integration.py` | 4,548 | 136 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_normalizer_and_phantoms.py` | 4,326 | 109 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_pipeline_natural_conversation.py` | 2,266 | 61 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_rag.py` | 2,037 | 51 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_rag_and_conflict_resolution.py` | 3,451 | 90 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_reader.py` | 4,655 | 126 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_retrieval.py` | 8,052 | 184 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_router.py` | 4,261 | 124 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_scope_config.py` | 6,624 | 160 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_session_state_anaphora.py` | 5,711 | 156 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_state_machine.py` | 4,915 | 138 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_steps_5_to_8.py` | 2,882 | 62 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_storage.py` | 6,704 | 172 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_tools.py` | 9,391 | 252 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_transcripts.py` | 2,641 | 77 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_two_tier_pricing.py` | 4,200 | 116 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_understander.py` | 5,583 | 152 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_validator.py` | 2,450 | 65 | `.py` | **Reviewed** | Test Suite File |
| `tests/test_web_hardening.py` | 12,089 | 323 | `.py` | **Reviewed** | Test Suite File |
| `tests/transcripts/sample_chat.json` | 1,199 | 52 | `.json` | **Reviewed** | Test Suite File |
