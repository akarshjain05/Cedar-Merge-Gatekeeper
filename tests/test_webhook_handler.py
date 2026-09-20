"""
Real tests against the real handler logic. Mocks DynamoDB with moto 
and stubs avp_client/github_client so this runs with no live AWS calls.
"""
import json
import os
import boto3
import pytest
from moto import mock_aws

os.environ["MEMBERS_TABLE_NAME"] = "members-test"
os.environ["POLICY_STORE_ID"] = "test-store"
os.environ["GITHUB_API_BASE_URL"] = "https://api.github.com"
os.environ["GITHUB_TOKEN_SECRET_ARN"] = "arn:aws:secretsmanager:us-east-1:000000000000:secret:test"
os.environ["GITHUB_WEBHOOK_SECRET_ARN"] = "arn:aws:secretsmanager:us-east-1:000000000000:secret:webhook"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"


from src.handlers import webhook_handler

@pytest.fixture
def members_table():
    # Reset singletons to prevent state leakage between tests
    webhook_handler.team_repository._table = None
    webhook_handler._dynamodb_table = None
    
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
        webhook_handler.avp_client, "batch_is_authorized",
        lambda policy_store_id, requests: [
            {"allowed": allowed, "policy_ids": [policy_id] if policy_id else [], "errors": []}
            for _ in requests
        ]
    )
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/src/auth/login.py"])
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_line_count", lambda repo, pr: 10)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_approvers", lambda repo, pr: [])
    
    # Mock Bedrock AI to just return a static string for testing
    monkeypatch.setattr(
        webhook_handler.bedrock_client, "generate_explanation", 
        lambda principal, policy_id, changed_path, lines_changed, decision: f"AI says {'yes' if decision == 'ALLOW' else 'no'} because of {policy_id}"
    )


def test_allows_security_to_approve_auth(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=True, policy_id="security-owns-auth")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    # Load realistic payload from fixture
    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Override for this specific test
    payload["pull_request"]["user"]["login"] = "alice"
    payload["sender"]["login"] = "bob"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "ALLOW"
    assert "security-owns-auth" in body["reason"]


def test_denies_self_approval(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="no-self-approval")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    payload["pull_request"]["user"]["login"] = "alice"
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
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
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status_neutral", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
        
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    assert "Degraded - GitHub API Failure" in response["body"]

def test_avp_failure_degrades_gracefully(members_table, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("AVP Unreachable")

    monkeypatch.setattr(webhook_handler.avp_client, "batch_is_authorized", _boom)
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status_neutral", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/src/main.py"])
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_line_count", lambda repo, pr: 10)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_approvers", lambda repo, pr: [])
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
        
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    assert "Degraded - AVP Failure" in response["body"]


def test_large_pr_allowed_for_senior_engineer(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=True, policy_id="engineering-default")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # 600 total lines changed
    payload["pull_request"]["additions"] = 400
    payload["pull_request"]["deletions"] = 200
    
    # Vikash is in senior-engineers
    payload["sender"]["login"] = "vikash"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "ALLOW"


def test_large_pr_denied_for_standard_engineer(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="large-pr-requires-senior")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # 600 total lines changed
    payload["pull_request"]["additions"] = 400
    payload["pull_request"]["deletions"] = 200
    
    # Alice is NOT in senior-engineers
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
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
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Override for this specific test
    payload["pull_request"]["user"]["login"] = "bob"
    # Alice is NOT in security-team
    payload["sender"]["login"] = "alice"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    assert "default-deny" in body["reason"]

def test_bedrock_fallback_uses_static_reason(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="some-policy")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    
    # Force Bedrock to fail
    monkeypatch.setattr(webhook_handler.bedrock_client, "generate_explanation", lambda *args, **kwargs: None)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    # Should use the static fallback message
    assert "Ask another reviewer to approve or check team permissions" in body["reason"]

def test_bedrock_ai_reason_used(members_table, monkeypatch):
    _stub_avp(monkeypatch, allowed=False, policy_id="some-policy")
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    
    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    assert "Gatekeeper AI:** AI says no because of some-policy" in body["reason"]

def test_merge_action_path(members_table, monkeypatch):
    """Proves the webhook_handler correctly delegates PR closed/merged events to the mergePR Cedar action."""
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/src/main.py"])
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.bedrock_client, "generate_explanation", lambda *a, **k: "AI Reason")
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_line_count", lambda repo, pr: 10)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_approvers", lambda repo, pr: [])

    called_action = []

    def mock_batch_is_authorized(policy_store_id, requests):
        if requests:
            called_action.append(requests[0].get("action_id"))
        return [{"allowed": True, "policy_ids": ["engineering-default"], "errors": []} for _ in requests]
        
    monkeypatch.setattr(webhook_handler.avp_client, "batch_is_authorized", mock_batch_is_authorized)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Mutate the payload to simulate a PR merge
    payload["action"] = "closed"
    payload.pop("review", None)
    payload["pull_request"]["merged"] = True
    payload["pull_request"]["user"]["login"] = "alice"
    payload["sender"]["login"] = "test-user"
    
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    assert called_action == ["mergePR"]

def test_denies_pr_when_a_non_first_non_auth_file_is_denied(members_table, monkeypatch):
    """Reproduces the exact scenario: /README.md + /src/payments/charge.py, only the second one denied."""
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: ["/README.md", "/src/payments/charge.py"])
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_line_count", lambda repo, pr: 10)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_approvers", lambda repo, pr: ["test-user"])
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.bedrock_client, "generate_explanation", lambda *a, **k: "AI Reason")

    requested_files = []

    def mock_batch_is_authorized(policy_store_id, requests):
        results = []
        for req in requests:
            file_path = req["context"]["changedPath"]["string"]
            requested_files.append(file_path)
            # Allow README, deny payments
            if file_path == "/README.md":
                results.append({"allowed": True, "policy_ids": ["engineering-default"], "errors": []})
            else:
                results.append({"allowed": False, "policy_ids": ["default-deny"], "errors": []})
        return results

    monkeypatch.setattr(webhook_handler.avp_client, "batch_is_authorized", mock_batch_is_authorized)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
        
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)
    
    body = json.loads(response["body"])
    assert body["decision"] == "DENY"
    
    # Assert both files were actually sent to Cedar
    assert "/README.md" in requested_files
    assert "/src/payments/charge.py" in requested_files

def test_empty_file_list_evaluates_as_unknown(members_table, monkeypatch):
    """Verifies that if GitHub returns 0 files, we evaluate ['/unknown'] and it is correctly processed."""
    monkeypatch.setattr(webhook_handler, "verify_signature", lambda e: True)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_changed_files", lambda repo, pr: [])
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_line_count", lambda repo, pr: 0)
    monkeypatch.setattr(webhook_handler.github_client, "get_pr_approvers", lambda repo, pr: ["test-user"])
    monkeypatch.setattr(webhook_handler.github_client, "set_commit_status", lambda *a, **k: None)
    monkeypatch.setattr(webhook_handler.github_client, "post_pr_comment", lambda *a, **k: None)

    requested_files = []

    def mock_batch_is_authorized(policy_store_id, requests):
        results = []
        for req in requests:
            file_path = req["context"]["changedPath"]["string"]
            requested_files.append(file_path)
            results.append({"allowed": True, "policy_ids": ["engineering-default"], "errors": []})
        return results

    monkeypatch.setattr(webhook_handler.avp_client, "batch_is_authorized", mock_batch_is_authorized)

    with open("tests/fixtures/real_pr_payload.json", "r") as f:
        payload = json.load(f)
    
    # Needs a custom headers mock for validation
    event = {"body": json.dumps(payload), "headers": {"x-github-event": "pull_request_review"}}
    response = webhook_handler.handler(event, None)

    assert response["statusCode"] == 200
    # It should have passed exactly one file string "/unknown" to Cedar for each user
    assert requested_files == ["/unknown", "/unknown"]
