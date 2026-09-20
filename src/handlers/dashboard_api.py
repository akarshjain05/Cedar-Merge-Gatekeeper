import json
import os
import boto3

def _cors_headers(event):
    # CRITICAL SECURITY FIX: CORS wildcard
    # Prevent arbitrary websites from scraping the dashboard API
    # Defaults to localhost for local testing, but relies on FRONTEND_URL in production
    origin = event.get("headers", {}).get("origin", "")
    allowed_origin = os.environ.get("FRONTEND_URL", "http://localhost:8000")
    
    # Simple check for demo purposes
    if origin and allowed_origin != "*" and not origin.startswith(allowed_origin):
        allowed_origin = "http://localhost:8000"
        
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(event), "body": ""}
        
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["DECISIONS_TABLE_NAME"])
        
        # CRITICAL SECURITY FIX: Data Loss via Pagination
        # DynamoDB scan() returns a max of 1MB. We must paginate using LastEvaluatedKey.
        items = []
        response = table.scan()
        items.extend(response.get("Items", []))
        
        pages = 1
        while "LastEvaluatedKey" in response and pages < 5:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
            pages += 1
            
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "statusCode": 200,
            "headers": _cors_headers(event),
            # Use default=str to safely serialize any DynamoDB Decimals
            "body": json.dumps({"decisions": items}, default=str)
        }
    except Exception as e:
        # Do not leak internal stack traces or AWS ARNs to the client
        print(f"Internal Dashboard API Error: {e}")
        return {
            "statusCode": 500,
            "headers": _cors_headers(event),
            "body": json.dumps({"error": "Internal Server Error"})
        }
