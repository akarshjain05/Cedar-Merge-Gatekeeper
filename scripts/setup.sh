#!/usr/bin/env bash
set -euo pipefail

echo "Installing AWS SAM CLI and AWS CLI (if missing)..."
command -v sam >/dev/null || brew install aws-sam-cli
command -v aws >/dev/null || brew install awscli

echo "Setting up Python virtual environment..."
python3.12 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt -r requirements-dev.txt

echo "Running the test suite..."
make test

echo "Done. Next: 'aws configure', then 'make build && make deploy'."
