import pytest
import cedarpy

def load_cedar():
    with open('policies/pr_policies.cedar') as f:
        policies = f.read()
    with open('policies/schema.cedarschema') as f:
        schema = f.read()
    return policies, schema

def evaluate(policies, schema, day_of_week: str, is_hotfix: bool, teams: list) -> bool:
    request = {
        "principal": 'CedarGatekeeper::GitHubUser::"vikash"',
        "action": 'CedarGatekeeper::Action::"mergePR"',
        "resource": 'CedarGatekeeper::PullRequest::"repo#1"',
        "context": {
            "changedPath": "/src/backend/app.py",
            "totalLinesChanged": 100,
            "prAuthor": {"__entity": {"type": "CedarGatekeeper::GitHubUser", "id": "alice"}},
            "activeTeams": teams,
            "dayOfWeek": day_of_week,
            "isHotfix": is_hotfix
        }
    }
    result = cedarpy.is_authorized(request, policies, "[]", schema)
    return result.decision == cedarpy.Decision.Allow

def test_friday_merges():
    policies, schema = load_cedar()
    
    # Monday merges are fine
    assert evaluate(policies, schema, "Monday", False, ["engineering-core"]) == True
    
    # Friday merges are blocked
    assert evaluate(policies, schema, "Friday", False, ["engineering-core"]) == False
    
    # Friday hotfix by core engineer is blocked
    assert evaluate(policies, schema, "Friday", True, ["engineering-core"]) == False
    
    # Friday hotfix by senior engineer is ALLOWED!
    assert evaluate(policies, schema, "Friday", True, ["senior-engineers"]) == True
    
def test_security_auth_path():
    policies, schema = load_cedar()
    request = {
        "principal": 'CedarGatekeeper::GitHubUser::"vikash"',
        "action": 'CedarGatekeeper::Action::"approvePR"',
        "resource": 'CedarGatekeeper::PullRequest::"repo#1"',
        "context": {
            "changedPath": "/src/auth/login.py",
            "totalLinesChanged": 50,
            "prAuthor": {"__entity": {"type": "CedarGatekeeper::GitHubUser", "id": "alice"}},
            "activeTeams": ["security-team"],
            "dayOfWeek": "Wednesday",
            "isHotfix": False
        }
    }
    assert cedarpy.is_authorized(request, policies, "[]", schema).decision == cedarpy.Decision.Allow
    
    # Core engineer shouldn't be able to approve auth paths
    request["context"]["activeTeams"] = ["engineering-core"]
    assert cedarpy.is_authorized(request, policies, "[]", schema).decision == cedarpy.Decision.Deny # Implicit Deny

def test_forbid_overrides_permit():
    policies, schema = load_cedar()
    request = {
        "principal": 'CedarGatekeeper::GitHubUser::"alice"',
        "action": 'CedarGatekeeper::Action::"approvePR"',
        "resource": 'CedarGatekeeper::PullRequest::"repo#1"',
        "context": {
            "changedPath": "/src/auth/login.py",
            "totalLinesChanged": 50,
            "prAuthor": {"__entity": {"type": "CedarGatekeeper::GitHubUser", "id": "alice"}},
            "activeTeams": ["security-team"],
            "dayOfWeek": "Wednesday",
            "isHotfix": False
        }
    }
    # Alice is on security team modifying /src/auth/ (matches Rule 1 Permit)
    # BUT Alice is the author, which matches Rule 2 (Forbid self-approval)
    # Cedar evaluation dictates Forbid always overrides Permit.
    result = cedarpy.is_authorized(request, policies, "[]", schema)
    assert result.decision == cedarpy.Decision.Deny
