import os
import json
import logging
from flask import Flask, request
from unittest.mock import patch

# Mock out team repository so it doesn't try to use DynamoDB
from src.handlers import team_repository
def fake_get_teams_for_user(username):
    # Hardcoded test data matching the DynamoDB seed script
    if username == "akarshjain05": return ["security-team", "engineering-core"]
    if username == "vikash": return ["senior-engineers"]
    if username == "test-user": return ["engineering-core"]
    return ["engineering-core"]
team_repository.get_teams_for_user = fake_get_teams_for_user

# Mock out Verified Permissions — implement Cedar rules directly in Python.
# This mirrors the exact logic in pr_policies.cedar without needing AWS.
from src.handlers import avp_client

def fake_is_authorized(policy_store_id, principal_id, action_id, resource_id, context):
    # Unwrap AVP wire format into plain values
    changed_path   = context.get("changedPath", {}).get("string", "/unknown")
    total_lines    = context.get("totalLinesChanged", {}).get("long", 0)
    pr_author_eid  = context.get("prAuthor", {}).get("entityIdentifier", {}).get("entityId", "")
    teams_raw      = context.get("activeTeams", {}).get("set", [])
    active_teams   = [t.get("string", "") for t in teams_raw]
    day_of_week    = context.get("dayOfWeek", {}).get("string", "")
    is_hotfix      = context.get("isHotfix", {}).get("boolean", False)

    # Match Cedar 'like "/src/auth/*"'
    is_auth_path   = changed_path.startswith("/src/auth/")
    is_large_pr    = total_lines > 500

    # Rule 5 (forbid): No Friday Merges unless it's a hotfix by a senior engineer
    if day_of_week == "Friday" and not (is_hotfix and "senior-engineers" in active_teams):
        return {"allowed": False, "policy_ids": ["no-friday-merges"], "errors": []}

    # Match Cedar 'like "/terraform/*"'
    is_infra_path = changed_path.startswith("/terraform/")
    if is_infra_path and day_of_week in ["Saturday", "Sunday"] and not (is_hotfix and "senior-engineers" in active_teams):
        return {"allowed": False, "policy_ids": ["no-weekend-infra"], "errors": []}

    # Rule 2 (forbid): No self-approvals
    if principal_id == pr_author_eid:
        return {"allowed": False, "policy_ids": ["no-self-approval"], "errors": []}

    # Rule 4 (forbid): Large PRs require senior engineers
    if is_large_pr and "senior-engineers" not in active_teams:
        return {"allowed": False, "policy_ids": ["large-pr-requires-senior"], "errors": []}

    # Rule 8 (forbid): Infrastructure code requires senior engineers 24/7
    if is_infra_path and "senior-engineers" not in active_teams:
        return {"allowed": False, "policy_ids": ["infra-requires-senior"], "errors": []}

    # Rule 7 (permit): Senior Break-Glass (Hotfix)
    if is_hotfix and "senior-engineers" in active_teams:
        return {"allowed": True, "policy_ids": ["senior-break-glass"], "errors": []}

    # Rule 1 (permit): Security team owns /auth/ path
    if is_auth_path and "security-team" in active_teams:
        return {"allowed": True, "policy_ids": ["security-owns-auth"], "errors": []}

    # Rule 3 (permit): Engineers can approve non-auth PRs
    if not is_auth_path and ("engineering-core" in active_teams or "senior-engineers" in active_teams):
        return {"allowed": True, "policy_ids": ["engineering-default"], "errors": []}

    # Implicit deny — no policy matched
    return {"allowed": False, "policy_ids": ["default-deny"], "errors": []}

def fake_batch_is_authorized(policy_store_id, requests):
    results = []
    for req in requests:
        principal_id = req["principal"]["entityId"]
        action_id = req["action"]["actionId"]
        resource_id = req["resource"]["entityId"]
        context = req["context"]["contextMap"]
        results.append(fake_is_authorized(policy_store_id, principal_id, action_id, resource_id, context))
    return results

avp_client.is_authorized = fake_is_authorized
avp_client.batch_is_authorized = fake_batch_is_authorized

# Bypass AWS entirely — inject secrets directly into the module-level cache
# so github_client never calls boto3.client("secretsmanager") at all.
import src.handlers.github_client as github_client
github_client._cached_token = os.environ.get("GITHUB_TOKEN", "dummy_token")
github_client._cached_webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "dummy_secret")

from src.handlers import webhook_handler

app = Flask(__name__)

# Basic logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    # Pass the request exactly as API Gateway would pass it to Lambda
    event = {
        "body": request.get_data(as_text=True),
        "headers": dict(request.headers)
    }
    
    try:
        response = webhook_handler.handler(event, None)
        return response["body"], response["statusCode"]
    except Exception as e:
        logger.error(f"Local Server Error: {e}")
        return str(e), 500

if __name__ == "__main__":
    print("🚀 Starting Cedar Merge Gatekeeper (Local Bypass Mode)")
    print("Listening on http://localhost:5001/webhook")
    print("Point ngrok to port 5001 to accept GitHub Webhooks!")
    app.run(port=5001, debug=True)
