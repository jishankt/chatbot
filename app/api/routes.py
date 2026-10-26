import time
import hmac
import hashlib
from flask import Blueprint, request, jsonify, render_template
from app.config import Config
from app.agent.pipeline import CX02Pipeline
from app.storage.messages import is_message_duplicate
from app.storage.leads import get_leads
from app.tools.pricing import load_catalog
from app.tools.quote import create_quote

api_bp = Blueprint("api", __name__)
pipeline = CX02Pipeline()


@api_bp.route("/", methods=["GET"])
@api_bp.route("/test", methods=["GET"])
def test_page():
    """Serves the interactive testing console web page."""
    return render_template("index.html")


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    catalog = load_catalog()
    products = catalog.get("products", {})
    return jsonify({
        "status": "healthy",
        "service": "cx02-sales-ai",
        "supported_model": "Citizen CX-02",
        "whitelisted_skus_count": len(products),
        "as_of": catalog.get("as_of"),
        "timestamp": time.time()
    }), 200


@api_bp.route("/chat", methods=["POST"])
def chat_endpoint():
    """
    Standard chat endpoint for web widget, test harness, and evaluation runner.
    Payload: {"message": str, "sender_id": Optional[str], "phone": Optional[str]}
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "").strip()
    sender_id = data.get("sender_id", data.get("phone", "web_user")).strip()
    phone = data.get("phone", "+971500000000").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    start_time = time.time()
    result = pipeline.process(
        user_message=message,
        sender_id=sender_id,
        channel="web",
        phone=phone
    )
    duration_ms = (time.time() - start_time) * 1000.0

    return jsonify({
        "reply": result["reply"],
        "intent": result.get("intent"),
        "priority": result.get("priority"),
        "tools_called": result.get("tools_called", []),
        "retrieval_count": len(result.get("chunks_retrieved", [])),
        "latency_ms": round(duration_ms, 2)
    }), 200


@api_bp.route("/quote", methods=["POST"])
def quote_endpoint():
    """Direct quotation endpoint."""
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    customer_name = data.get("customer_name", "Valued Customer")
    phone = data.get("phone")

    res = create_quote(items=items, customer_name=customer_name, phone=phone)
    status_code = 200 if res.get("status") == "success" else 400
    return jsonify(res), status_code


@api_bp.route("/leads", methods=["GET"])
def leads_endpoint():
    """Retrieve captured CRM leads."""
    leads = get_leads(limit=100)
    return jsonify({"leads": leads, "count": len(leads)}), 200


def _handle_whatsapp_verification():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == Config.WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Verification token mismatch", 403


def _handle_whatsapp_incoming():
    # 1. Signature validation (if secret is configured)
    if Config.WHATSAPP_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256="):
            return jsonify({"status": "error", "message": "Invalid signature format"}), 401
        expected_sig = "sha256=" + hmac.new(
            Config.WHATSAPP_APP_SECRET.encode("utf-8"),
            request.data,
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return jsonify({"status": "error", "message": "Invalid signature"}), 403

    payload = request.get_json(silent=True) or {}
    entries = payload.get("entry", [])

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                msg_id = msg.get("id")

                # Deduplication check via SQLite
                if msg_id and is_message_duplicate(msg_id):
                    continue

                from_num = msg.get("from", "Unknown")
                text_body = msg.get("text", {}).get("body", "").strip()

                if text_body:
                    pipeline.process(
                        user_message=text_body,
                        sender_id=from_num,
                        channel="whatsapp",
                        phone=from_num,
                        message_id=msg_id
                    )

    # Always return 200 to acknowledge Meta webhook
    return jsonify({"status": "EVENT_RECEIVED"}), 200


@api_bp.route("/webhook", methods=["GET"])
@api_bp.route("/webhook/whatsapp", methods=["GET"])
def webhook_get():
    return _handle_whatsapp_verification()


@api_bp.route("/webhook", methods=["POST"])
@api_bp.route("/webhook/whatsapp", methods=["POST"])
def webhook_post():
    return _handle_whatsapp_incoming()
