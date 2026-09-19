import sys
import os

# Ensure the src directory is in the path
sys.path.append(os.path.abspath("src"))

from handlers.bedrock_client import generate_rejection_explanation

print("🤖 Requesting AI explanation from Bedrock (Claude 3 Haiku)...\n")

ai_response = generate_rejection_explanation(
    principal="junior-dev",
    policy_id="security-owns-auth",
    changed_path="/src/auth/login.py",
    lines_changed=30
)

if ai_response:
    print("✅ Successfully generated AI comment:\n")
    print("-" * 40)
    print(ai_response)
    print("-" * 40)
else:
    print("❌ Failed to generate AI comment. Check AWS credentials and permissions.")
