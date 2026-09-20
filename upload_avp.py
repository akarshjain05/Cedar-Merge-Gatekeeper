import boto3
import json
import re

client = boto3.client('verifiedpermissions', region_name='us-east-1')
stacks = boto3.client('cloudformation', region_name='us-east-1').describe_stacks(StackName='cedar-gatekeeper')
store_id = [opt['OutputValue'] for opt in stacks['Stacks'][0]['Outputs'] if opt['OutputKey'] == 'PolicyStoreId'][0]

with open('policies/pr_policies.cedar') as f:
    policies_str = f.read()

# CRITICAL FIX: Regex Fragility
# The previous regex only matched rules explicitly starting with "// Rule N:"
# and ignored multi-line comments. This new regex captures all consecutive
# comment lines directly above any permit/forbid block.
matches = re.finditer(r'((?://.*?\n)+)(permit.*?};|forbid.*?};)', policies_str, re.MULTILINE | re.DOTALL)

for page in client.get_paginator('list_policies').paginate(policyStoreId=store_id):
    for p in page.get('policies', []):
        client.delete_policy(policyStoreId=store_id, policyId=p['policyId'])

for m in matches:
    # Remove all '// ' prefixes from the captured comment block and strip whitespace
    desc = re.sub(r'//\s*', '', m.group(1)).strip()
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
