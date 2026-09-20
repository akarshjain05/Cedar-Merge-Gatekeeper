"""
Lambda entry point: parses a GitHub webhook, gathers context,
calls AVP to authorize a PR merge or approval, logs the decision,
and updates the GitHub PR status via the github_client.
"""
import json
import os
import logging

from . import avp_client, team_repository, github_client, bedrock_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)


import hmac
import hashlib
import uuid
from datetime import datetime, timezone
import boto3

_dynamodb_table = None

def _get_table():
    global _dynamodb_table
    if _dynamodb_table is None:
        table_name = os.environ.get("DECISIONS_TABLE_NAME")
        if table_name:
            dynamodb = boto3.resource("dynamodb")
            _dynamodb_table = dynamodb.Table(table_name)
    return _dynamodb_table

def _log_decision_to_db(decision_log: dict, delivery_id: str):
    try:
        table = _get_table()
        if table:
            decision_log["id"] = delivery_id
            decision_log["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            table.put_item(Item=decision_log)
    except Exception as e:
        logger.error(f"Failed to record decision to DB: {e}")

def verify_signature(event):
    secret = github_client.get_webhook_secret().encode("utf-8")
    headers = event.get("headers", {})
    signature_header = next((v for k, v in headers.items() if k.lower() == "x-hub-signature-256"), "")
    if not signature_header:
        return False
        
    body = event.get("body") or ""
    expected_signature = "sha256=" + hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)

def handler(event, context):
    logger.info(f"RAW_WEBHOOK_PAYLOAD: {json.dumps(event)}")
    
    # Phase 6: Verify Signature before processing
    if not verify_signature(event):
        return {"statusCode": 401, "body": "Unauthorized"}
        
    headers = event.get("headers", {})
    delivery_id = next((v for k, v in headers.items() if k.lower() == "x-github-delivery"), str(uuid.uuid4()))

    table = _get_table()
    if table:
        try:
            table.put_item(
                Item={"id": delivery_id, "timestamp": datetime.now(timezone.utc).isoformat(), "status": "PROCESSING"},
                # CRITICAL SECURITY FIX: Use 'verdict' instead of 'id' for the lock condition.
                # If we use 'attribute_not_exists(id)', a Lambda crash will leave the DB with
                # a permanent PROCESSING lock, blocking all future GitHub retries.
                # Since the final decision log writes a 'verdict' attribute, checking for 'verdict'
                # allows GitHub retries to safely overwrite a stuck/crashed PROCESSING lock.
                ConditionExpression="attribute_not_exists(verdict)"
            )
        except Exception as e:
            if "ConditionalCheckFailedException" in str(e.__class__.__name__):
                logger.info(f"Idempotency hit: delivery {delivery_id} already processed.")
                return {"statusCode": 200, "body": "Already processed"}
            else:
                logger.error(f"DynamoDB error during idempotency check: {e}")

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {"statusCode": 200, "body": "Ignored malformed JSON"}

    # CRITICAL FIX: Explicit Webhook Event Type Validation
    # Relying solely on body structure allows crafted payloads to bypass intent.
    event_type = next((v for k, v in headers.items() if k.lower() == "x-github-event"), "")
    
    if event_type == "ping":
        return {"statusCode": 200, "body": "pong"}
        
    if event_type not in ["pull_request", "pull_request_review"]:
        return {"statusCode": 200, "body": f"Ignored event type: {event_type}"}

    if "pull_request" not in body:
        return {"statusCode": 200, "body": "Ignored event"}

    action = body.get("action")
    is_review_approved = "review" in body and action == "submitted" and body["review"].get("state") == "approved"
    
    pr = body["pull_request"]
    is_merged = action == "closed" and pr.get("merged") is True
    
    if is_review_approved:
        action_id = "approvePR"
    elif is_merged:
        action_id = "mergePR"
    else:
        return {"statusCode": 200, "body": "Ignored non-actionable event"}
    
    try:
        repo_name = body["repository"]["full_name"]
        pr_number = pr["number"]
        sender = body.get("sender", {}).get("login", "")
        author = pr["user"]["login"]
        
        # CRITICAL SECURITY FIX: Sender validation
        # Prevent empty string injection which could bypass self-approval checks
        # or evaluate against an anonymous principal.
        if not sender or not author:
            return {"statusCode": 200, "body": "Ignored payload with missing sender or author"}
            
        lines_changed = pr.get("additions", 0) + pr.get("deletions", 0)
        head_sha = pr["head"]["sha"]
    except KeyError:
        return {"statusCode": 200, "body": "Ignored malformed PR payload"}

    # 1. GitHub API Failure Resilience
    try:
        files = github_client.get_pr_changed_files(repo_name, pr_number)
        
        # When a PR Review is submitted, the webhook payload often omits additions/deletions. 
        # We must explicitly fetch it from GitHub to prevent 0-line bypasses.
        lines_changed = github_client.get_pr_line_count(repo_name, pr_number)
        
        # Fetch all approvers to prevent the "last approver wins" overwrite bug
        approvers = []
        if action_id == "approvePR":
            approvers = github_client.get_pr_approvers(repo_name, pr_number)
            if sender not in approvers:
                approvers.append(sender)
        else:
            approvers = [sender]
            
    except Exception as e:
        decision_log = {
            "principal": sender,
            "action": action_id,
            "resource": f"{repo_name}#{pr_number}",
            "verdict": "NEUTRAL",
            "policyId": "N/A",
            "reason": "GITHUB_API_FAILURE",
            "error": str(e)
        }
        logger.error(json.dumps(decision_log))
        _log_decision_to_db(decision_log, delivery_id)
        
        reason = "⚠️ **Merge check degraded** — Unable to fetch changed files from GitHub due to API limits or errors."
        _notify_github_neutral(repo_name, head_sha, pr_number, reason)
        return {"statusCode": 200, "body": "Degraded - GitHub API Failure"}

    resource_id = f"{repo_name}#{pr_number}"

    pr_title = pr.get("title", "")
    day_of_week = datetime.now(timezone.utc).strftime("%A")
    is_hotfix = "[HOTFIX]" in pr_title.upper()

    # 2. AVP Failure Resilience & Multi-file Multi-Approver Evaluation
    try:
        final_result = None
        final_changed_path = None
        
        if not files:
            files = ["/unknown"]

        # Build the batch requests
        batch_requests = []
        for f in files:
            normalized_f = f if f.startswith("/") else f"/{f}"
            for approver in approvers:
                teams = team_repository.get_teams_for_user(approver)
                batch_requests.append({
                    "file": normalized_f, # Custom tracking key
                    "principal_id": approver,
                    "action_id": action_id,
                    "resource_id": resource_id,
                    "context": {
                        "changedPath": {"string": normalized_f},
                        "totalLinesChanged": {"long": lines_changed},
                        "prAuthor": {"entityIdentifier": {"entityType": "CedarGatekeeper::GitHubUser", "entityId": author}},
                        "activeTeams": {"set": [{"string": t} for t in teams]},
                        "dayOfWeek": {"string": day_of_week},
                        "isHotfix": {"boolean": is_hotfix},
                    }
                })

        # Send to AWS Verified Permissions Batch API
        batch_results = avp_client.batch_is_authorized(
            policy_store_id=os.environ.get("POLICY_STORE_ID", "store"),
            requests=batch_requests
        )

        # Merge results: A file is approved if ANY approver is authorized to approve it
        file_approval_status = { (f if f.startswith("/") else f"/{f}"): False for f in files }
        denied_file_results = {} # Track the last denied result per file in case it completely fails
        
        for req, res in zip(batch_requests, batch_results):
            if res["allowed"]:
                file_approval_status[req["file"]] = True
            else:
                denied_file_results[req["file"]] = res
                
        # Check if ALL files were approved
        all_files_approved = all(file_approval_status.values())
        
        if all_files_approved:
            # Success! Grab any successful result for the logging output
            result = next(res for res in batch_results if res["allowed"])
            changed_path = files[0] if files[0].startswith("/") else f"/{files[0]}"
        else:
            # Find a file that was NOT approved and report it
            failed_file = next(f for f, allowed in file_approval_status.items() if not allowed)
            result = denied_file_results[failed_file]
            changed_path = failed_file
        
    except Exception as e:
        decision_log = {
            "principal": sender,
            "action": action_id,
            "resource": resource_id,
            "verdict": "NEUTRAL",
            "policyId": "N/A",
            "reason": "AVP_UNREACHABLE",
            "error": str(e)
        }
        logger.error(json.dumps(decision_log))
        _log_decision_to_db(decision_log, delivery_id)
        
        reason = "⚠️ **Merge check degraded** — Unable to reach AWS Verified Permissions. Please try again later or contact an administrator."
        _notify_github_neutral(repo_name, head_sha, pr_number, reason)
        return {"statusCode": 200, "body": "Degraded - AVP Failure"}

    if result.get("errors"):
        logger.warning(f"AVP Evaluation Errors: {result['errors']}")
        
    decision = "ALLOW" if result["allowed"] else "DENY"
    policy_id = result['policy_ids'][0] if result.get('policy_ids') else "default-deny"
    ai_reason = bedrock_client.generate_explanation(
        principal=sender,
        policy_id=policy_id,
        changed_path=changed_path,
        lines_changed=lines_changed,
        decision=decision
    )
    
    if result["allowed"]:
        if ai_reason:
            reason = f"✅ **Merge check passed**\n\n**Gatekeeper AI:** {ai_reason}"
        else:
            reason = f"✅ **Merge check passed** — `{policy_id}` permitted this approval.\n`{sender}` is authorized to approve this PR."
    else:
        if ai_reason:
            reason = f"🚫 **Merge check failed**\n\n**Gatekeeper AI:** {ai_reason}"
        else:
            reason = f"🚫 **Merge check failed** — policy `{policy_id}` denied this request.\nAsk another reviewer to approve or check team permissions."
        
    decision_log = {
        "principal": sender,
        "action": action_id,
        "resource": resource_id,
        "verdict": decision,
        "policyId": policy_id,
        "reason": reason
    }
    
    logger.info(json.dumps(decision_log))
    
    # Write directly to the fallback DynamoDB decisions table
    _log_decision_to_db(decision_log, delivery_id)
    
    # The commit status UI needs a short string without markdown
    short_status = "Approved by Gatekeeper AI" if result["allowed"] else "Denied by Gatekeeper AI"
    
    # Update GitHub
    try:
        github_client.set_commit_status(repo_name, head_sha, result["allowed"], short_status)
        github_client.post_pr_comment(repo_name, pr_number, reason)
    except Exception as e:
        logger.exception("Failed to update GitHub after AVP decision.")

    return {
        "statusCode": 200,
        "body": json.dumps({"decision": decision, "reason": reason}),
    }

def _notify_github_neutral(repo_name: str, head_sha: str, pr_number: int, reason: str):
    try:
        # We need to tell the github_client to send neutral. 
        # For now, we will just post the comment. If github_client supports neutral, we call it.
        # But our github_client.set_check_run_status only takes allowed (bool). We must update it.
        github_client.set_commit_status_neutral(repo_name, head_sha, reason)
        github_client.post_pr_comment(repo_name, pr_number, reason)
    except Exception:
        logger.exception("Failed to notify GitHub of neutral status.")
