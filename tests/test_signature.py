import pytest
import hmac
import hashlib
from src.handlers.webhook_handler import verify_signature

def test_verify_signature_valid(monkeypatch):
    monkeypatch.setattr("src.handlers.github_client.get_webhook_secret", lambda: "secret")
    body = "hello world"
    expected = "sha256=" + hmac.new(b"secret", body.encode("utf-8"), hashlib.sha256).hexdigest()
    
    event = {
        "body": body,
        "headers": {"X-Hub-Signature-256": expected}
    }
    assert verify_signature(event) is True

def test_verify_signature_invalid(monkeypatch):
    monkeypatch.setattr("src.handlers.github_client.get_webhook_secret", lambda: "secret")
    event = {
        "body": "hello world",
        "headers": {"X-Hub-Signature-256": "sha256=invalid"}
    }
    assert verify_signature(event) is False

def test_verify_signature_no_body(monkeypatch):
    monkeypatch.setattr("src.handlers.github_client.get_webhook_secret", lambda: "secret")
    expected = "sha256=" + hmac.new(b"secret", b"", hashlib.sha256).hexdigest()
    event = {
        "headers": {"X-Hub-Signature-256": expected}
    }
    # Body is missing (None), should not crash and should return True
    assert verify_signature(event) is True
