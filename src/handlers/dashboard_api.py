import json
import os
import boto3

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}
        
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["DECISIONS_TABLE_NAME"])
        response = table.scan()
        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "statusCode": 200,
            "headers": _cors_headers(),
            "body": json.dumps({"decisions": items})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": str(e)})
        }
