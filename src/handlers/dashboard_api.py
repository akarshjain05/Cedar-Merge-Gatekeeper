import os
import json
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb")

def handler(event, context):
    table_name = os.environ.get("DECISIONS_TABLE_NAME")
    if not table_name:
        return {"statusCode": 500, "body": "DECISIONS_TABLE_NAME not configured"}
        
    table = dynamodb.Table(table_name)
    
    # For a hackathon demo, a Scan is perfect. In prod we'd use a GSI.
    response = table.scan()
    items = response.get("Items", [])
    
    # Sort items by timestamp descending
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Add CORS headers so the static HTML file can call it
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Content-Type": "application/json"
        },
        "body": json.dumps({"decisions": items}),
    }
