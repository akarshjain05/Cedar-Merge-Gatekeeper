import cedarpy

with open('policies/pr_policies.cedar') as f: policies = f.read()
with open('policies/schema.cedarschema') as f: schema = f.read()

request = {
    "principal": 'CedarGatekeeper::GitHubUser::"vikash"',
    "action": 'CedarGatekeeper::Action::"approvePR"',
    "resource": 'CedarGatekeeper::PullRequest::"repo#1"',
    "context": {
        "changedPath": "/src/auth/login.py",
        "totalLinesChanged": 100,
        "prAuthor": {"__entity": {"type": "CedarGatekeeper::GitHubUser", "id": "alice"}},
        "activeTeams": ["security-team"],
        "dayOfWeek": "Monday",
        "isHotfix": False
    }
}

try:
    result = cedarpy.is_authorized(request, policies, "[]", schema)
    print(result.decision)
    print(result.diagnostics.errors)
except Exception as e:
    print(f"Error: {e}")
