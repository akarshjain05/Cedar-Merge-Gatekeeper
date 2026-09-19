"""
Wrapper around boto3's `verifiedpermissions` client's IsAuthorized call.
"""
import boto3

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("verifiedpermissions")
    return _client


_policy_descriptions = {}

def get_policy_description(policy_store_id: str, policy_id: str) -> str:
    global _policy_descriptions
    if policy_id not in _policy_descriptions:
        client = _get_client()
        try:
            resp = client.get_policy(policyStoreId=policy_store_id, policyId=policy_id)
            desc = resp.get("policyDefinition", {}).get("static", {}).get("description")
            statement = resp.get("policyDefinition", {}).get("static", {}).get("statement")
            
            if desc:
                _policy_descriptions[policy_id] = desc
            elif statement:
                # If no description exists, return the exact Cedar code so the AI can read it!
                _policy_descriptions[policy_id] = f"Cedar Policy Code:\n{statement}"
            else:
                _policy_descriptions[policy_id] = policy_id
        except Exception:
            _policy_descriptions[policy_id] = policy_id
            
    return _policy_descriptions[policy_id]

def is_authorized(policy_store_id: str, principal_id: str, action_id: str, resource_id: str, context: dict) -> dict:
    """
    Returns {"allowed": bool, "policy_ids": [...], "errors": [...]}.
    """
    client = _get_client()
    response = client.is_authorized(
        policyStoreId=policy_store_id,
        principal={"entityType": "CedarGatekeeper::GitHubUser", "entityId": principal_id},
        action={"actionType": "CedarGatekeeper::Action", "actionId": action_id},
        resource={"entityType": "CedarGatekeeper::PullRequest", "entityId": resource_id},
        context={"contextMap": context}
    )
    
    policy_ids = []
    for d in response.get("determiningPolicies", []):
        raw_id = d["policyId"]
        policy_ids.append(get_policy_description(policy_store_id, raw_id))
        
    return {
        "allowed": response["decision"] == "ALLOW",
        "policy_ids": policy_ids,
        "errors": response.get("errors", []),
    }
