import json
import boto3
import logging

logger = logging.getLogger()

_client = None

def _get_client():
    global _client
    if _client is None:
        # Dynamically inherit the region from the AWS Lambda execution environment
        _client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _client

def generate_explanation(principal: str, policy_id: str, changed_path: str, lines_changed: int, decision: str) -> str:
    """
    Uses Anthropic Claude 3 Haiku via Amazon Bedrock to generate a friendly, 
    helpful explanation for why a PR merge was allowed or denied based on the Cedar policy.
    """
    
    if decision == "ALLOW":
        scenario_text = "A pull request approval was just ALLOWED by our AWS Verified Permissions (Cedar) authorization engine."
        task_text = "Please write a short, friendly, congratulatory message to the engineer explaining that their approval passed."
    else:
        scenario_text = "A pull request was just DENIED by our AWS Verified Permissions (Cedar) authorization engine."
        task_text = "Please explain to the engineer why it was denied and what they should do next."

    prompt = f"""You are a helpful, senior DevOps assistant named Gatekeeper AI.
{scenario_text}
{task_text} Keep it concise, friendly, and under 4 sentences.

Details:
- Engineer (Principal): {principal}
- Sensitive path changed (if any): {changed_path}
- Total lines changed: {lines_changed}
- Determining Policy ID or Cedar Code: {policy_id}

Known policies:
- security-owns-auth: Only the security-team can approve changes to /src/auth/*
- no-self-approval: Authors cannot approve or merge their own pull requests.
- large-pr-requires-senior: PRs over 500 lines require someone from senior-engineers.
- engineering-default: Standard engineers can approve non-auth PRs under 500 lines.
- default-deny: If no specific permit policy matched, it defaults to deny.

Based on the Details above, carefully deduce exactly WHICH of these known policies triggered this {decision} decision, and clearly explain why to the engineer.
Output ONLY the markdown-formatted message to post on the PR. Do not include introductory text.
"""

    try:
        response = _get_client().converse(
            modelId="amazon.nova-lite-v1:0",
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            inferenceConfig={"maxTokens": 300, "temperature": 0.4}
        )
        return response['output']['message']['content'][0]['text'].strip()
    except Exception as e:
        logger.error(f"Bedrock invocation failed: {e}")
        return None
