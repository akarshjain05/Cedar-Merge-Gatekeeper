"""
GitHub REST client: fetch a token from Secrets Manager once per cold
start, cache it, and use it for outbound GitHub API calls (Commit Statuses, PR comments).
"""
import os
import json
import boto3
import requests

_cached_token = None
_cached_webhook_secret = None

def _get_token() -> str:
    global _cached_token
    if _cached_token is None:
        client = boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId=os.environ["GITHUB_TOKEN_SECRET_ARN"])
        _cached_token = json.loads(secret["SecretString"])["token"]
    return _cached_token

def get_webhook_secret() -> str:
    global _cached_webhook_secret
    if _cached_webhook_secret is None:
        client = boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId=os.environ["GITHUB_WEBHOOK_SECRET_ARN"])
        _cached_webhook_secret = json.loads(secret["SecretString"])["secret"]
    return _cached_webhook_secret


def set_commit_status(repo_name: str, head_sha: str, allowed: bool, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    
    state = "success" if allowed else "failure"

    url = f"{base_url}/repos/{repo_name}/statuses/{head_sha}"
    
    # Truncate description to 140 chars per GitHub API limit and remove newlines (causes 422)
    reason = reason.replace("\n", " ")
    if len(reason) > 137:
        reason = reason[:137] + "..."
        
    requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github.v3+json"
        },
        json={
            "state": state,
            "description": reason,
            "context": "Cedar Merge Gatekeeper"
        },
        timeout=5,
    ).raise_for_status()

def set_commit_status_neutral(repo_name: str, head_sha: str, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/statuses/{head_sha}"
    
    reason = reason.replace("\n", " ")
    if len(reason) > 137:
        reason = reason[:137] + "..."
        
    requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github.v3+json"
        },
        json={
            "state": "error",
            "description": reason,
            "context": "Cedar Merge Gatekeeper"
        },
        timeout=5,
    ).raise_for_status()


def post_pr_comment(repo_name: str, pr_number: int, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/issues/{pr_number}/comments"
    
    requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github.v3+json"
        },
        json={"body": reason},
        timeout=5,
    ).raise_for_status()

def get_pr_line_count(repo_name: str, pr_number: int) -> int:
    """Fetches the actual PR from GitHub to get true line count (additions + deletions)."""
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/pulls/{pr_number}"
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github.v3+json"
        },
        timeout=5
    )
    response.raise_for_status()
    data = response.json()
    return data.get("additions", 0) + data.get("deletions", 0)

def get_pr_approvers(repo_name: str, pr_number: int) -> list[str]:
    """Fetches all users who have submitted an APPROVED review for the PR."""
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/pulls/{pr_number}/reviews"
    
    user_latest_state = {}
    headers = {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    while url:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        for review in response.json():
            if review.get("user"):
                username = review["user"]["login"]
                state = review.get("state")
                
                # CRITICAL SECURITY FIX: Stale Approvals
                # GitHub returns all reviews chronologically. We must track the LATEST effective
                # state per user. If they approve, but later request changes or their review
                # gets dismissed, we must revoke their approval. We ignore "COMMENTED" because
                # leaving a comment doesn't revoke an existing approval.
                if state in ["APPROVED", "CHANGES_REQUESTED", "DISMISSED"]:
                    user_latest_state[username] = state
                
        # Handle GitHub API pagination
        url = None
        if "Link" in response.headers:
            links = response.headers["Link"].split(",")
            for link in links:
                if 'rel="next"' in link:
                    url = link[link.find("<")+1:link.find(">")]
                    break
                    
    # Only return users whose absolute latest effective review is "APPROVED"
    return [user for user, state in user_latest_state.items() if state == "APPROVED"]

def get_pr_changed_files(repo_name: str, pr_number: int) -> list[str]:
    """Fetches all changed file paths for a PR, handling pagination."""
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/pulls/{pr_number}/files"
    
    files = []
    headers = {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    while url:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        for item in response.json():
            filename = item.get("filename")
            if filename:
                files.append(filename)
            
            # CRITICAL SECURITY FIX: File Rename Evasion
            # If a file was renamed or moved out of a secure directory (like /src/auth/),
            # we MUST evaluate the original path as well. Otherwise, an attacker could
            # move a secure file to a public directory and bypass Cedar path restrictions.
            prev_filename = item.get("previous_filename")
            if prev_filename:
                files.append(prev_filename)
        # Handle GitHub API pagination
        url = None
        if "Link" in response.headers:
            links = response.headers["Link"].split(",")
            for link in links:
                if 'rel="next"' in link:
                    url = link[link.find("<")+1 : link.find(">")]
                    break
    
    return files
