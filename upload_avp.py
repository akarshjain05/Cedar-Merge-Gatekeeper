import boto3
import json
import re

client = boto3.client('verifiedpermissions', region_name='us-east-1')
stacks = boto3.client('cloudformation', region_name='us-east-1').describe_stacks(StackName='cedar-gatekeeper')
store_id = [opt['OutputValue'] for opt in stacks['Stacks'][0]['Outputs'] if opt['OutputKey'] == 'PolicyStoreId'][0]

with open('policies/pr_policies.cedar') as f:
    policies_str = f.read()

# We can match the comment above the rule and the rule itself
matches = re.finditer(r'// (Rule \d+:.*?)\n(permit.*?};|forbid.*?};)', policies_str, re.MULTILINE | re.DOTALL)

for page in client.get_paginator('list_policies').paginate(policyStoreId=store_id):
    for p in page.get('policies', []):
        client.delete_policy(policyStoreId=store_id, policyId=p['policyId'])

for m in matches:
    desc = m.group(1).strip()
    rule = m.group(2).strip()
    try:
        client.create_policy(
            policyStoreId=store_id,
            definition={
                'static': {
                    'description': desc,
                    'statement': rule
                }
            }
        )
        print(f"Uploaded: {desc}")
    except Exception as e:
        print(f"Failed to upload: {desc}\nError: {e}")
