# 03_API_INVENTORY.md - Comprehensive Endpoint & RPC Audit

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
