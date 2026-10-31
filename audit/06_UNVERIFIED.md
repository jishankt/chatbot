# 06_UNVERIFIED.md - Unverified Items & External Environmental Dependencies

In accordance with Audit Rule 2 (*EVIDENCE OR NOTHING*), the following items could not be 100% verified via automated local execution due to external service credentials, production network requirements, or live third-party dependencies.

| Item ID | Component | Claim / Behavior Under Review | Reason Unverified Locally | Action Required from User / Operator to Verify |
| :--- | :--- | :--- | :--- | :--- |
| **UNV-01** | WhatsApp Cloud API | Real-time outbound delivery of messages via Meta Graph API (`app/whatsapp/client.py:send_whatsapp_message`). | No live Meta `WHATSAPP_TOKEN` or test phone number configured in local `.env`. | Provide test WhatsApp Cloud API credentials to verify real webhook handoff and outbound payload receipt. |
| **UNV-02** | OpenRouter Live Model | Response latency, rate limits, and actual output token structure from `meta-llama/llama-3.3-70b-instruct`. | `OPENROUTER_API_KEY` is not populated; system gracefully fell back to local Ollama `qwen2.5:7b`. | Provide OpenRouter sandbox API key to test live provider latency and streaming compatibility. |
| **UNV-03** | Nginx Edge Rate Limiting | Burst connection rejection (HTTP 429) at 20 req/s defined in `scripts/nginx.conf`. | Local dev environment executes against Gunicorn directly; Nginx reverse proxy daemon is not running locally. | Deploy test container behind active Nginx instance and run ApacheBench / wrk load test. |
| **UNV-04** | Offbox S3/Rsync Backup | Off-box automated database backup replication (`scripts/offbox_backup_copy.py`). | External offsite storage credentials (`OFFBOX_BACKUP_DEST`) not configured in development environment. | Run backup script in staging environment with verified remote storage destination. |
