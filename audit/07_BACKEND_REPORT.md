# 07_BACKEND_REPORT.md - Deep-Dive Backend, Data, Concurrency & Runtime Audit

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
