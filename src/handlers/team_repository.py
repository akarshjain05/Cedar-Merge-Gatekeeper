"""
DynamoDB-backed lookup of a GitHub user's team memberships.
"""
import os
import boto3

_table = None


def _get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb")
        _table = dynamodb.Table(os.environ["MEMBERS_TABLE_NAME"])
    return _table


def get_teams_for_user(username: str) -> list[str]:
    response = _get_table().get_item(Key={"username": username})
    item = response.get("Item")
    return list(item["teams"]) if item and "teams" in item else []
