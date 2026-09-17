# Hackathon Master Execution Checklist

This document tracks all the manual, real-world execution steps you need to perform once the hackathon clock starts. 

## Phase 1: Repository Initialization
*To ensure your git history officially starts inside the event window:*
- [ ] Run `git init` in this directory.
- [ ] Run `git add .`
- [ ] Run `git commit -m "Cedar-Based Merge Gatekeeper for CI/CD - Initial Commit for the AWS First Commit Hackathon. Contributors: Akarsh & Vikash"`
- [ ] Create a new **Public** repository on GitHub.
- [ ] Add the remote and `git push` your code.
- [ ] Both teammates clone the repository locally and verify push access.

## Phase 3: Live Environment Stand-Up
- [ ] Verify your local AWS profile / SAM CLI is pointing to the correct Builder Center AWS account (`aws sts get-caller-identity`).
- [ ] Copy the contents of `policies/schema.cedarschema` and paste it into the [Cedar Playground](https://www.cedarpolicy.com/en/playground) or AWS Verified Permissions console to validate the syntax.
- [ ] Do the same for `policies/pr_policies.cedar`.

## Phase 5: Skeleton Infrastructure Deployment
- [ ] Run `make build` and `make deploy` to provision the AWS stack via SAM.
- [ ] Copy the `ApiUrl` output by the deployment.
- [ ] Manually test the endpoint using curl to ensure it logs payloads to CloudWatch:
      `curl -X POST <your-api-url> -H "Content-Type: application/json" -d '{"test": "hello webhook"}'`

## Phase 6: GitHub Integration Setup
- [ ] Generate a GitHub Personal Access Token (PAT).
- [ ] Generate a Webhook Secret string (e.g., a random UUID).
- [ ] Go to your AWS Secrets Manager and update:
  - `GitHubTokenSecret` -> `{"token":"<your-real-github-pat>"}`
  - `GitHubWebhookSecret` -> `{"secret":"<your-webhook-secret>"}`
- [ ] Go to your scratch GitHub repository settings -> Webhooks -> Add Webhook:
  - Payload URL: `<your-api-url>`
  - Content type: `application/json`
  - Secret: `<your-webhook-secret>`
  - Events: Send me **everything** (or specifically Pull Requests and Pull Request Reviews).

## Phase 8: Team-Membership Data Layer
- [ ] Find the real physical name of your DynamoDB table in the AWS Console (e.g., `sam-app-MembersTable-1A2B3C`).
- [ ] Run the seeding script to populate your test users:
      `./scripts/seed_dynamodb.sh <Your-Actual-Table-Name>`

## Phase 9 & 10: End-to-End Validation
- [ ] **Test Self-Approval Ban**: Open a PR as `akarshjain05` and try to approve it as `akarshjain05`. Verify GitHub blocks it and posts the `no-self-approval` reason.
- [ ] **Test Path-Restricted Policy (Allow)**: Open a PR touching `/src/auth/` and approve it with an account in `security-team`. Verify it passes.
- [ ] **Test Path-Restricted Policy (Deny)**: Open a PR touching `/src/auth/` and try to approve it with an account that is NOT in `security-team`. Verify it gets denied.

## Phase 11: Decision Feedback Loop
- [ ] Visually verify that the Check-Run output and PR comments render correctly on GitHub's UI (Markdown formatting, Emojis, Code Blocks).

## Phase 12: Mid-Build Health Check & Mentor Consultation
- [ ] Consult with an AWS Mentor (in-person at Bangalore or online). Ask them these specific questions:
  1. *Are the IAM permissions scoped to our Lambda execution role appropriately tight for a production Gatekeeper?*
  2. *We chose to pass teams as Request Context instead of Entity Attributes to avoid syncing a persistent entity store. Does this align with AWS best practices for a lightweight CI/CD Gatekeeper?*
  3. *Does our serverless architecture (API Gateway + Lambda + AVP + DynamoDB) hold up as a highly cost-effective approach for high-volume GitHub webhooks?*
- [ ] If Vikash is in Bangalore and Akarsh is remote, Vikash must record the mentor's answers in writing and share them with Akarsh immediately to prevent secondhand misinterpretation.
- [ ] Ensure any feedback received results in minor tweaks (<= 1 hour), not a major redesign.

## Phase 13: Error Handling & Resilience Validation
*Intentionally break the system to ensure it degrades gracefully:*
- [ ] **GitHub API Failure**: Temporarily scramble your `GitHubTokenSecret` in AWS Secrets Manager. Trigger a webhook and ensure a `neutral` check-run appears in GitHub indicating API failure, instead of a silent crash.
- [ ] **AVP Down/Misconfigured**: Temporarily change the `POLICY_STORE_ID` environment variable to a fake string. Trigger a webhook and ensure it degrades to a `neutral` check-run and logs `AVP_UNREACHABLE` specifically for the dashboard.
- [ ] **Malformed Payload**: Send a completely mangled JSON body via the AWS Lambda "Test Event" tab. Verify it immediately returns a `200 OK` (so GitHub doesn't retry indefinitely).

## Phase 14: The Centerpiece — Live Policy-Flip Rehearsal
*This is the most important part of your final video submission. Practice it until it is flawless.*
- [ ] **Rehearsal 1 (The Baseline)**: Open a PR touching `/src/auth/` with a non-security user. Verify it is DENIED. Go to the AWS AVP Console, edit the `security-owns-auth` policy, and change the team requirement from `security-team` to `engineering-core`. Re-trigger the webhook. Verify the exact same PR is now ALLOWED instantly without redeploying any code.
- [ ] **Rehearsal 2 (The Reversal)**: Change the policy back to `security-team` in the AWS Console. Re-trigger the webhook. Verify the PR flips back to DENIED.
- [ ] **Rehearsal 3 (The Line Count)**: Open a PR with >500 lines changed. Verify it is DENIED by the large-PR rule. Go to the AVP Console and edit the policy condition from `500` to `1000`. Re-trigger the webhook. Verify it is now ALLOWED.
- [ ] **Recording Practice**: Run through one of these scenarios while actually recording your screen (using whatever software you will use for the final submission) to ensure the pacing fits within the time limit and both teammates know their cues.

## Phase 15: Stretch Goal — Large-PR Senior-Reviewer Policy
*Verify your 3rd Cedar policy rule behaves exactly as expected.*
- [ ] **Test Large PR (Allow)**: Open a PR with more than 500 lines changed (total additions + deletions). Approve it using a GitHub account linked to the `senior-engineers` team (e.g., `vikash`). Verify the Check-Run passes and posts the approval.
- [ ] **Test Large PR (Deny)**: Open the exact same >500 line PR. Attempt to approve it using an account in `engineering-core` but NOT `senior-engineers`. Verify it instantly blocks the merge with the `large-pr-requires-senior` reason.

## Phase 16: Stretch Goal — Decision-Log Dashboard
*To win the Best UI track, you must verify the dashboard renders real data.*
- [ ] Run `make build` and `make deploy` to push the new `DashboardFunction` and `DecisionsTable` infrastructure to AWS.
- [ ] Get your new API Gateway URL from the deployment output.
- [ ] Open `dashboard/index.html` locally in your code editor and replace `const API_URL = "REPLACE_ME_WITH_YOUR_API_URL/decisions";` with the real URL.
- [ ] Open `dashboard/index.html` in your browser. Verify it renders beautiful header stats, a responsive Chart.js doughnut chart, and a live feed of decisions flowing in directly from your AWS DynamoDB table!

## Phase 17: End-to-End Regression Freeze
*STOP ALL FEATURE WORK NOW. Re-run everything you built from scratch. Do this together.*
- [ ] **Re-Test MVP Policy 1**: Self-Approval Ban (Deny).
- [ ] **Re-Test MVP Policy 2**: `/auth/` Path Restriction (Allow & Deny).
- [ ] **Re-Test Stretch Policy**: >500 Lines (Allow & Deny).
- [ ] **Re-Test Resilience 1**: GitHub Token Broken (Verify Neutral status).
- [ ] **Re-Test Resilience 2**: AVP `POLICY_STORE_ID` Broken (Verify Neutral status).
- [ ] **Re-Test Resilience 3**: Malformed Webhook JSON (Verify 200 OK).
- [ ] **Verify Dashboard**: Confirm that all of these fresh test decisions from the morning run populated correctly into the live dashboard.

## Phase 18: Demo Video Scripting, Recording & Editing
*The most critical submission artifact. Keep it tight (2-3 minutes max).*
- [ ] **Record Multiple Takes**: Do not submit the first take if you stumble. Record the centerpiece policy-flip multiple times and stitch the cleanest one.
- [ ] **Narrate the AWS Services**: Specifically say *which* AWS service is doing the work (e.g., "API Gateway triggers Lambda", "Verified Permissions evaluates the Cedar policy"). This directly targets the "Built on AWS" judging criteria.
- [ ] **The Serverless Pitch**: Conclude the video with a one-sentence pitch about cost: *"Nothing in this pipeline runs, or costs anything, between pull requests."*
- [ ] **Time Box**: Be merciless with the editing. A clean 3-minute video showing just the MVP and the policy flip is better than a rushed 4-minute video trying to cram the dashboard in.
- [ ] **Live Call Prep**: Be prepared to either play this video on the Sunday live call or perform the identical script live within a strict 3-minute window.

## Phase 19: Writeup, Builder Center Post & Submission Packaging
*Double-check compliance and publish the final blog post.*
- [ ] **AWS Builder Center Post**: Write the final submission post. Explain what CODEOWNERS can't do, how Cedar solves it, what went wrong during the build (the pain points!), and exactly which AWS services you used. This doubles as your Best Blog entry.
- [ ] **Commit History Check**: Run `git log` and review your GitHub repository. Ensure your commits are organically distributed across Thursday through Sunday. 
- [ ] **README Verification**: The `README.md` has already been updated with the AI Tool Disclosure and Third-Party Licenses. Review it to make sure you agree with the wording before submitting.
- [ ] **Final Submission**: Package everything up, submit the form, and get ready for the Sunday live call!

## Phase 20: Final Submission, Live Demo Call & Wrap-Up
*Submit early, breathe, and nail the live presentation.*
- [ ] **Preview the Submission Form**: Do this immediately. Check for unexpected fields or video file-size limits so you aren't scrambling at the last minute.
- [ ] **Submit Early**: Submit the project *well before* the deadline. Do not hold it back chasing "10 more minutes of polish." Late submissions are strictly disqualified.
- [ ] **Final Social Post**: Post a quick update tagging the organizers to announce that the project has been submitted.
- [ ] **The Live Call**: Join the call together. Have the 3-minute script ready. Be prepared to answer questions on your architectural choices, specifically the Entity Attributes vs. Request Context choice and the serverless cost breakdown (zero cost between PRs).
- [ ] **Celebrate**: You built a resilient, dynamic, serverless authorization gatekeeper on AWS. Awesome work.
