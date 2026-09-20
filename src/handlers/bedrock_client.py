import json
import boto3
import logging
import os

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
    Uses Amazon Nova Lite via Amazon Bedrock to generate a friendly, 
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
- Determining Policy Description: {policy_id}

Based on the Details above, carefully read the Determining Policy Description that triggered this {decision} decision, and clearly explain why it happened to the engineer. Focus heavily on the exact wording of the Determining Policy.
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
