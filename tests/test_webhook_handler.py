"""
Real tests against the real handler logic. Mocks DynamoDB with moto 
and stubs avp_client/github_client so this runs with no live AWS calls.
"""
import json
import os
import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("MEMBERS_TABLE_NAME", "members-test")
os.environ.setdefault("POLICY_STORE_ID", "test-store")
os.environ.setdefault("GITHUB_API_BASE_URL", "https://api.github.com")
os.environ.setdefault("GITHUB_TOKEN_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:000000000000:secret:test")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:000000000000:secret:webhook")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


from src.handlers import webhook_handler


@pytest.fixture
def members_table():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=os.environ["MEMBERS_TABLE_NAME"],
            KeySchema=[{"AttributeName": "username", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "username", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"username": "alice", "teams": ["engineering-core"]})
        table.put_item(Item={"username": "bob", "teams": ["security-team"]})
        table.put_item(Item={"username": "vikash", "teams": ["senior-engineers"]})
        yield table


def _stub_avp(monkeypatch, allowed: bool, policy_id: str | None = None):
    monkeypatch.setattr(
        webhook_handler.avp_client, "is_authorized",
        lambda **kwargs: {"allowed": allowed, "policy_ids": [policy_id] if policy_id else [], "errors": []},
    )
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/src/auth/login.py"])


def test_allows_security_to_approve_auth(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=True, policy_id="security-owns-auth")
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    # Load realistic payload from fixture
    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Override for this specific test
    payload["pull_request"]["user"]["login"] = "alice"
    payload["sender"]["login"] = "bob"
    
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "ALLOW"
    assert "security-owns-auth" in body["reason"]


def test_denies_self_approval(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="no-self-approval")
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    payload["pull_request"]["user"]["login"] = "alice"
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    assert "no-self-approval" in body["reason"]


def test_malformed_json_returns_200_to_prevent_retries(members_table, monkeypatch):
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    event = {"body": "{"}
    response = webhook_handler.handler(event, None)
    assert response["statusCode"] == 200

def test_github_api_failure_degrades_gracefully(members_table, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("GitHub API rate limited")

    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", _boom)
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_neutral", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
        
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    assert "Degraded - GitHub API Failure" in response["body"]

def test_avp_failure_degrades_gracefully(members_table, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("AVP Unreachable")

    monkeypatch.setattr(webhook_handler.avp_client, "is_authorized", _boom)
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_neutral", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/src/main.py"])
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
        
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    assert "Degraded - AVP Failure" in response["body"]


def test_large_pr_allowed_for_senior_engineer(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=True, policy_id="engineering-default")
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # 600 total lines changed
    payload["pull_request"]["additions"] = 400
    payload["pull_request"]["deletions"] = 200
    
    # Vikash is in senior-engineers
    payload["sender"]["login"] = "vikash"
    
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "ALLOW"


def test_large_pr_denied_for_standard_engineer(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="large-pr-requires-senior")
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # 600 total lines changed
    payload["pull_request"]["additions"] = 400
    payload["pull_request"]["deletions"] = 200
    
    # Alice is NOT in senior-engineers
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    assert "large-pr-requires-senior" in body["reason"]

def test_looks_up_real_team_membership_from_dynamodb(members_table, monkeypatch):
    from src.handlers import team_repository
    assert team_repository.get_teams_for_user("alice") == ["engineering-core"]
    assert team_repository.get_teams_for_user("nobody") == []

def test_denies_non_security_to_approve_auth(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="default-deny")
    monkeypatch.setattr(webhook_handler.github_client, "set_check_run_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Override for this specific test
    payload["pull_request"]["user"]["login"] = "bob"
    # Alice is NOT in security-team
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload)}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    assert "default-deny" in body["reason"]
