#!/bin/bash
# Seed the DynamoDB Members table with test data for the MVP demo scenarios.
# Usage: ./scripts/seed_dynamodb.sh <TableName>

TABLE_NAME=${1:-"MembersTable"}

echo "Seeding DynamoDB table: $TABLE_NAME"

# User 1: Security Team member (can approve /auth/* PRs)
aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{"username": {"S": "akarshjain05"}, "teams": {"L": [{"S": "security-team"}, {"S": "engineering-core"}]}}'
echo "Added akarshjain05 to security-team & engineering-core"

# User 2: Senior Engineer (can approve PRs > 500 lines)
aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{"username": {"S": "vikash"}, "teams": {"L": [{"S": "engineering-core"}, {"S": "senior-engineers"}]}}'
echo "Added vikash to engineering-core & senior-engineers"

# User 3: Standard Engineer (default policies)
aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{"username": {"S": "test-user"}, "teams": {"L": [{"S": "engineering-core"}]}}'
echo "Added test-user to engineering-core"

echo "Database seeded successfully!"
