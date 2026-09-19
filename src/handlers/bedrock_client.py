import json
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_bedrock_client = None

def _get_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime")
    return _bedrock_client

def generate_explanation(principal: str, policy_id: str, changed_path: str, action: str, allowed: bool, reason: str) -> str:
    """
    Uses Amazon Nova (first-party model to bypass Marketplace payment issues) to generate a human-readable explanation.
    """
    decision = "ALLOW" if allowed else "DENY"
    prompt = f"""
Explain this Cedar policy decision to a developer in one short, friendly paragraph.
Decision: {decision}
Policy Reason: {reason}
Principal: {principal}
Action: {action}
Resource: {changed_path}

Format it using GitHub markdown. Keep it under 3 sentences. Be clear if it was allowed or denied.
"""

    try:
        response = _get_client().converse(
            modelId="amazon.nova-lite-v1:0",
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            system=[{"text": "You are a friendly GitHub security auditor explaining why a PR was approved or denied based on Cedar policies."}],
            inferenceConfig={"maxTokens": 300}
        )
        return response['output']['message']['content'][0]['text']
    except Exception as e:
        logger.error(f"Bedrock invocation failed: {str(e)}")
        # Graceful fallback if Bedrock is unreachable
        icon = "✅" if allowed else "❌"
        return f"{icon} **Merge check passed** — `{reason}` permitted this approval.\n`{principal}` is authorized to approve this PR."
