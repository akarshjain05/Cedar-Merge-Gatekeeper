# Cedar Merge Gatekeeper for CI/CD test

🚀 **[View Live Dashboard](https://main.d3ofi8gfbpsdj6.amplifyapp.com/)**

A serverless application that uses **AWS Verified Permissions** (Cedar) to evaluate complex pull request approvals that standard `CODEOWNERS` files cannot express. It acts as a dynamic merge gatekeeper, ensuring that code approvals comply with team hierarchy, file-path restrictions, and line-count thresholds before allowing code to merge.

## Why Cedar over CODEOWNERS?
Standard GitHub `CODEOWNERS` is static. It can enforce "Team X owns Path Y", but it cannot enforce conditional logic like:
- "Nobody can self-approve their own Pull Request."
- "Pull requests over 500 lines require a Senior Engineer's approval."

By decoupling the authorization logic from application code and moving it into AWS Verified Permissions, security and engineering teams can instantly update merge rules in the AWS Console without redeploying a single line of CI/CD code.

## Security & Resilience Features
- **Strict Event Gating**: The gatekeeper ignores standard PR open/synchronize noise, safely triggering authorization evaluation *only* when a `pull_request_review` approval or a direct `merge` is submitted.
- **Fail-Closed API Fallbacks**: If the GitHub API rate-limits the Lambda or AWS Verified Permissions goes down, the gatekeeper falls back to a secure `NEUTRAL` degraded state (rather than failing open).
- **Exact Path Matching**: Python path validation accurately normalizes and enforces absolute path prefixing to ensure 1:1 parity with the Cedar `like "/src/auth/*"` schemas, preventing false-positive bypassed checks.
- **HMAC Hardened**: Full request signature validation verified comprehensively in unit tests.

## What We Learned (Hackathon Journey)
Building this over the last few days was a massive learning experience. Four days ago, we set out to build a highly-resilient security tool, and we walked away having conquered exactly what we set out to learn:
- **A service we had never touched**: We had never used **AWS Verified Permissions (Cedar)** before Thursday. We learned how to write decoupled policy-as-code, define custom entity schemas, and map them to dynamic JSON contexts.
- **A first deploy**: We learned the hard way that local unit testing isn't enough. We successfully navigated our **first true cloud deployment** using AWS SAM, discovering and fixing critical namespace mismatches and API rate-limiting vulnerabilities that only appear in a live AWS environment. 
- **A first agent**: We learned how to effectively pair-program alongside an autonomous AI agent (Google Deepmind's Antigravity). Rather than just generating code, we used the agent as an architectural sounding board to harden our fail-closed resilience logic and correctly map Cedar namespaces.

## Architecture

1. **GitHub** sends a webhook event (PR or Review) to an **API Gateway**.
2. **AWS Lambda** validates the HMAC signature, then fetches paginated PR metadata (files changed, line counts) via the GitHub REST API.
3. **Lambda** looks up the actor's team memberships in **DynamoDB**.
4. **Lambda** constructs a request context and queries **AWS Verified Permissions** (Cedar) for authorization.
5. **Verified Permissions** returns an `ALLOW` or explicit `DENY` decision, attaching the specific policy ID that triggered the denial.
6. **Lambda** writes the decision to a secondary **DynamoDB Decisions Table**.
7. **Lambda** updates the GitHub PR Check-Run status (success/neutral/failure) and posts a markdown comment explaining the exact reason.
8. A **Serverless UI Dashboard** (securely hosted on **AWS Amplify**) reads from the Decisions Table to visualize metrics via Chart.js.

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
