import hmac
import hashlib
import json
import pytest
from app.main import create_app
from app.config import Config


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["supported_model"] == "Citizen CX-02"
    assert data["whitelisted_skus_count"] == 6


def test_web_page_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Citizen CX-02 Sales AI" in res.text
    assert "Kepler Tech LLC" in res.text

    res_test = client.get("/test")
    assert res_test.status_code == 200
    assert "Citizen CX-02 Sales AI" in res_test.text


def test_chat_endpoint_price(client):
    res = client.post("/chat", json={"message": "What is the price of the Citizen CX-02 printer?"})
    assert res.status_code == 200
    data = res.get_json()
    assert "4,385.00" in data["reply"]
    assert data["intent"] == "price"


def test_chat_endpoint_guardrail(client):
    res = client.post("/chat", json={"message": "Do you sell DNP DS620?"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["intent"] == "guardrails"
    assert "kepler tech" in data["reply"].lower() or "citizen" in data["reply"].lower()


def test_quote_endpoint(client):
    res = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "Dubai Media City"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["subtotal"] == 4385.0


def test_whatsapp_verify(client):
    res = client.get("/webhook?hub.mode=subscribe&hub.verify_token=cx02_sales_verify_token&hub.challenge=test_challenge_123")
    assert res.status_code == 200
    assert res.text == "test_challenge_123"

    # Bad token
    res_bad = client.get("/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=test")
    assert res_bad.status_code == 403


def test_whatsapp_post_hmac_and_deduplication(client, monkeypatch):
    secret = "test_webhook_secret_key"
    monkeypatch.setattr(Config, "WHATSAPP_APP_SECRET", secret)

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid.TEST1001",
                        "from": "+971509998877",
                        "text": {"body": "How much is the Citizen CX-02?"}
                    }]
                }
            }]
        }]
    }
    raw_data = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_data, hashlib.sha256).hexdigest()

    # 1. Invalid signature format
    res_bad_fmt = client.post("/webhook", data=raw_data, headers={"X-Hub-Signature-256": "invalid_format", "Content-Type": "application/json"})
    assert res_bad_fmt.status_code == 401

    # 2. Tampered signature
    res_tampered = client.post("/webhook", data=raw_data, headers={"X-Hub-Signature-256": "sha256=1234567890abcdef", "Content-Type": "application/json"})
    assert res_tampered.status_code == 403

    # 3. Valid first message
    res_valid = client.post("/webhook", data=raw_data, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert res_valid.status_code == 200
    assert res_valid.get_json()["status"] == "EVENT_RECEIVED"

    # 4. Duplicate message ID should be deduplicated and still return 200
    res_dup = client.post("/webhook", data=raw_data, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert res_dup.status_code == 200
    assert res_dup.get_json()["status"] == "EVENT_RECEIVED"


def test_leads_endpoint_auth(client, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_API_KEY", "super_secret_admin_token")

    # 1. No token -> 401
    res_no_auth = client.get("/leads")
    assert res_no_auth.status_code == 401
    assert "Unauthorized" in res_no_auth.get_json()["error"]

    # 2. Wrong token -> 401
    res_wrong = client.get("/leads", headers={"Authorization": "Bearer wrong_token"})
    assert res_wrong.status_code == 401

    # 3. Valid token -> 200
    res_ok = client.get("/leads", headers={"Authorization": "Bearer super_secret_admin_token"})
    assert res_ok.status_code == 200
    assert "leads" in res_ok.get_json()


def test_handoffs_endpoint_auth(client, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_API_KEY", "super_secret_admin_token")

    # 1. No token -> 401
    res_no_auth = client.get("/handoffs")
    assert res_no_auth.status_code == 401
    assert "Unauthorized" in res_no_auth.get_json()["error"]

    # 2. Wrong token -> 401
    res_wrong = client.get("/handoffs", headers={"Authorization": "Bearer wrong_token"})
    assert res_wrong.status_code == 401

    # 3. Valid token -> 200
    res_ok = client.get("/handoffs", headers={"Authorization": "Bearer super_secret_admin_token"})
    assert res_ok.status_code == 200
    assert "handoffs" in res_ok.get_json()


def test_whatsapp_outbound_live_dispatch(monkeypatch):
    from unittest.mock import MagicMock
    from app.whatsapp.client import send_whatsapp_message
    import requests

    monkeypatch.setattr(Config, "WHATSAPP_API_TOKEN", "mock_meta_token_xyz")
    monkeypatch.setattr(Config, "WHATSAPP_PHONE_NUMBER_ID", "123456789012345")
    monkeypatch.setattr(Config, "WHATSAPP_GRAPH_API_VERSION", "v21.0")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": [{"id": "wamid.OUTBOUND123"}]}

    recorded_call = {}
    def mock_post(url, headers=None, json=None, timeout=None):
        recorded_call["url"] = url
        recorded_call["headers"] = headers
        recorded_call["json"] = json
        return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    result = send_whatsapp_message(to="+971508901641", text="Hello from Kepler Tech!")
    assert result["status"] == "sent"
    assert "v21.0" in recorded_call["url"]
    assert "123456789012345" in recorded_call["url"]
    assert recorded_call["headers"]["Authorization"] == "Bearer mock_meta_token_xyz"
    assert recorded_call["json"]["messaging_product"] == "whatsapp"
    assert recorded_call["json"]["text"]["body"] == "Hello from Kepler Tech!"


def test_whatsapp_production_fail_closed(client, monkeypatch):
    monkeypatch.setattr(Config, "ENV", "production")
    monkeypatch.setattr(Config, "WHATSAPP_APP_SECRET", "")
    monkeypatch.setattr(Config, "WHATSAPP_DEV_OVERRIDE", False)

    res = client.post("/webhook", json={"test": True})
    assert res.status_code == 500
    assert "unconfigured in production" in res.get_json()["message"]


def test_web_session_isolation_and_cookie_assignment(client):
    res = client.post("/chat", json={"message": "Hello from web browser"})
    assert res.status_code == 200
    data = res.get_json()
    assert "sender_id" in data
    assert data["sender_id"].startswith("web:")
    
    # Check that cookie was set
    cookie = res.headers.get("Set-Cookie")
    assert cookie is not None
    assert "web_session_id=" in cookie
    assert "HttpOnly" in cookie


def test_history_endpoint_unauthorized_isolation(client):
    # Public unauthenticated request cannot read arbitrary phone number history without valid session cookie
    res = client.get("/history?sender_id=+971509998877")
    assert res.status_code == 401
    data = res.get_json()
    assert "error" in data

    # Admin with Bearer token can query any sender_id
    admin_res = client.get(
        "/history?sender_id=test_admin_lookup",
        headers={"Authorization": f"Bearer {Config.ADMIN_API_KEY}"}
    )
    assert admin_res.status_code == 200
    admin_data = admin_res.get_json()
    assert admin_data["sender_id"] == "test_admin_lookup"

