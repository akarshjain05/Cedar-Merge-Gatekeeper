# Cedar Merge Gatekeeper for CI/CD test1

A serverless application that uses **AWS Verified Permissions** (Cedar) to evaluate complex pull request approvals that standard `CODEOWNERS` files cannot express. It acts as a dynamic merge gatekeeper, ensuring that code approvals comply with team hierarchy, file-path restrictions, and line-count thresholds before allowing code to merge.

## Why Cedar over CODEOWNERS?
Standard GitHub `CODEOWNERS` is static. It can enforce "Team X owns Path Y", but it cannot enforce conditional logic like:
- "Nobody can self-approve their own Pull Request."
- "Pull requests over 500 lines require a Senior Engineer's approval."

By decoupling the authorization logic from application code and moving it into AWS Verified Permissions, security and engineering teams can instantly update merge rules in the AWS Console without redeploying a single line of CI/CD code.

## Architecture

1. **GitHub** sends a webhook event (PR or Review) to an **API Gateway**.
2. **AWS Lambda** validates the HMAC signature, then fetches paginated PR metadata (files changed, line counts) via the GitHub REST API.
3. **Lambda** looks up the actor's team memberships in **DynamoDB**.
4. **Lambda** constructs a request context and queries **AWS Verified Permissions** (Cedar) for authorization.
5. **Verified Permissions** returns an `ALLOW` or explicit `DENY` decision, attaching the specific policy ID that triggered the denial.
6. **Lambda** writes the decision to a secondary **DynamoDB Decisions Table**.
7. **Lambda** updates the GitHub PR Check-Run status (success/neutral/failure) and posts a markdown comment explaining the exact reason.
8. A **Serverless UI Dashboard** reads from the Decisions Table to visualize metrics via Chart.js.

## Running it

```bash
# 1. Install dependencies
./scripts/setup.sh

# 2. Run the test suite (100% Passing)
make test

# 3. Deploy infrastructure via AWS SAM
make build && make deploy

# 4. Load Cedar schemas and policies into Verified Permissions
make load-policies
```

## AI Tool Disclosure
In compliance with hackathon rules, we disclose the use of the following AI tools used during the planning and build process:
- **Google Deepmind's Agentic Assistant (Antigravity)**: Used extensively for architectural planning, drafting the Cedar schema, mocking the AWS API integrations during local testing, and structuring our deployment scripts.

## Third-Party Libraries & Licenses
- **Chart.js** (MIT License): Used in the `dashboard/index.html` file to render the decision distribution doughnut chart.
- **TailwindCSS** (MIT License): Used via CDN for rapid styling of the dashboard UI.
- **Feather Icons** (MIT License): Used for SVG iconography in the dashboard.
