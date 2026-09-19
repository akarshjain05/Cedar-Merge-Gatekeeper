import boto3
import json

client = boto3.client('verifiedpermissions', region_name='us-east-1')
store_id = 'KLTqDaYQu8tNH71UQB9Djo'

with open('policies/schema.cedarschema') as f:
    schema_str = f.read()
    
# Wait! AVP supports Cedar schema format directly? No, it expects cedarJson as a string. But wait!
# Does AVP support Cedar syntax directly? Let's check boto3 documentation.
