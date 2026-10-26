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
    assert "specialize exclusively" in data["reply"].lower()


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
