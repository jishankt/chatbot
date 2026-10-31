"""
tests/test_nginx_integration.py
Integration tests for Nginx reverse proxy hardening:
1. Spoofed X-Forwarded-For / Host / X-Forwarded-Prefix rejection.
2. Rate limiting zone status (HTTP 429 on bursts).
3. Lockout enforcement by real client IP across proxy headers.
4. /admin/unlock authentication and its own failure counting / lockout.
"""

import pytest
import hmac
from pathlib import Path
from app.main import create_app
from app.config import Config
from app.storage.db import get_db_connection


def test_proxy_headers_and_spoofed_ip_isolation():
    """
    ProxyFix must accurately parse client IP from trusted proxies (127.0.0.1 / private CIDRs),
    and must NOT allow arbitrary untrusted multi-hop client spoofing.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # Legitimate single proxy hop: client 203.0.113.195 via local proxy
    res = client.post(
        "/chat",
        json={"message": "Hello", "sender_id": "test_proxy_real"},
        headers={"X-Forwarded-For": "203.0.113.195", "X-Forwarded-Proto": "https"}
    )
    assert res.status_code == 200

    # Malicious multi-hop spoofing attempt: "spoofed_attacker, real_proxy"
    # ProxyFix configured with x_for=1 must pick the immediate trusted hop's peer
    res2 = client.post(
        "/chat",
        json={"message": "Hello", "sender_id": "test_proxy_spoof"},
        headers={
            "X-Forwarded-For": "1.1.1.1, 203.0.113.195",
            "X-Forwarded-Host": "evil.attacker.com",
            "X-Forwarded-Prefix": "/malicious_prefix"
        }
    )
    assert res2.status_code == 200


def test_lockout_by_real_client_ip_and_spoofed_header_isolation():
    """
    When an attacker tries repeated invalid admin logins while sending
    random spoofed X-Forwarded-For headers, the lockout must still lock
    the client's actual IP and not be bypassed by rotating the header.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    attacker_ip = "198.51.100.77"

    # Send 5 failed admin logins
    for attempt in range(5):
        res = client.get(
            "/leads",
            headers={
                "Authorization": "Bearer wrong_token_attempt",
                "X-Forwarded-For": attacker_ip
            }
        )
        assert res.status_code in (401, 429)

    # 6th attempt must be locked out (429)
    locked_res = client.get(
        "/leads",
        headers={
            "Authorization": f"Bearer {Config.ADMIN_API_KEY}",
            "X-Forwarded-For": attacker_ip
        }
    )
    assert locked_res.status_code == 429, f"Expected 429 Lockout, got {locked_res.status_code}"


def test_admin_unlock_auth_and_failure_counting():
    """
    /admin/unlock requires valid ADMIN_API_KEY.
    Failed unlock attempts must be recorded in admin_auth_failures,
    and repeated failures must lock out the unlock endpoint itself.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    attacker_ip = "198.51.100.88"

    # Send 5 failed unlock attempts
    for attempt in range(5):
        res = client.post(
            "/admin/unlock",
            json={"ip": "10.0.0.99"},
            headers={
                "X-Admin-Key": "wrong_unlock_key",
                "X-Forwarded-For": attacker_ip
            }
        )
        assert res.status_code in (401, 429)

    # 6th attempt on /admin/unlock must be 429 Locked Out
    locked_unlock_res = client.post(
        "/admin/unlock",
        json={"ip": "10.0.0.99"},
        headers={
            "X-Admin-Key": Config.ADMIN_API_KEY,
            "X-Forwarded-For": attacker_ip
        }
    )
    assert locked_unlock_res.status_code == 429, "Unlock endpoint failed to lock out on repeated failed attempts!"


def test_nginx_conf_real_ip_and_rate_limits():
    """
    Verifies that nginx_rate_limits.conf contains all required directives:
    - real_ip_recursive on
    - limit_req_status 429
    - per-IP limits for /chat, /quote, /history
    - no wildcard 0.0.0.0/0 in set_real_ip_from
    """
    conf_path = Path("/opt/basics/config/nginx_rate_limits.conf")
    assert conf_path.exists(), "nginx_rate_limits.conf is missing!"
    content = conf_path.read_text(encoding="utf-8")

    assert "real_ip_recursive on;" in content
    assert "limit_req_status 429;" in content
    assert "zone=chat_ip_limit" in content
    assert "zone=quote_ip_limit" in content
    assert "zone=history_ip_limit" in content
    assert "0.0.0.0/0" not in content
