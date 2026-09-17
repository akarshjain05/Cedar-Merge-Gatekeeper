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
    return {
        "allowed": response["decision"] == "ALLOW",
        "policy_ids": [d["policyId"] for d in response.get("determiningPolicies", [])],
        "errors": response.get("errors", []),
    }
