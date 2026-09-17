"""
GitHub REST client: fetch a token from Secrets Manager once per cold
start, cache it, and use it for outbound GitHub API calls (Check Runs, PR comments).
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


def set_check_run_status(repo_name: str, head_sha: str, allowed: bool, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    
    status = "completed"
    conclusion = "success" if allowed else "failure"

    url = f"{base_url}/repos/{repo_name}/check-runs"
    try:
        requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_get_token()}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={
                "name": "Cedar Merge Gatekeeper",
                "head_sha": head_sha,
                "status": status,
                "conclusion": conclusion,
                "output": {
                    "title": "Cedar Authorization Result",
                    "summary": reason
                }
            },
            timeout=5,
        ).raise_for_status()
    except Exception as e:
        print(f"Mocked setting check run status failed or is disabled: {e}")

def set_check_run_neutral(repo_name: str, head_sha: str, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/check-runs"
    try:
        requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_get_token()}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={
                "name": "Cedar Merge Gatekeeper",
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": "neutral",
                "output": {
                    "title": "Cedar Authorization Degraded",
                    "summary": reason
                }
            },
            timeout=5,
        ).raise_for_status()
    except Exception as e:
        print(f"Failed to set neutral status: {e}")

def post_pr_comment(repo_name: str, pr_number: int, reason: str) -> None:
    base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
    url = f"{base_url}/repos/{repo_name}/issues/{pr_number}/comments"
    
    try:
        requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_get_token()}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={"body": reason},
            timeout=5,
        ).raise_for_status()
    except Exception as e:
        print(f"Failed to post comment: {e}")

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
        try:
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            
            for item in response.json():
                files.append(item.get("filename"))
                
            # Handle GitHub API pagination
            # The 'Link' header looks like: <https://api.github.com/...>; rel="next", <...>; rel="last"
            url = None
            if "Link" in response.headers:
                links = response.headers["Link"].split(",")
                for link in links:
                    if 'rel="next"' in link:
                        url = link[link.find("<")+1 : link.find(">")]
                        break
        except Exception as e:
            print(f"Failed to fetch PR files: {e}")
            break
            
    return files
