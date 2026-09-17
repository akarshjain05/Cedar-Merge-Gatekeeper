# Architecture & Design Decisions

## Data Modeling: Entity Attributes vs. Request Context

**Decision: Request Context**

After evaluating the tradeoffs, we have explicitly decided to model team membership and PR metadata using **Request Context** instead of Entity Attributes. 

### Rationale:
While entity attributes are idiomatic for Cedar, they require maintaining a synced persistent entity store, which consumes valuable setup time during a time-constrained build. The context-based approach allows us to build the authorization context dynamically on every webhook call without relying on a pre-loaded entity store. 

By modeling teams as a `Set<String>` passed in the context (e.g. `context.activeTeams`), we avoid complex hierarchy setups (`principal in Team::"..."`) in Cedar. Instead, our policies evaluate simple Set conditions (e.g. `context.activeTeams.contains("security-team")`). This approach was proven reliable during our practice lab and keeps the application logic agile.

## DynamoDB Table Schema
Because we are passing teams via context, our DynamoDB table (`members`) is kept as thin as possible, serving strictly as a fast look-up for a user's active team memberships.

- **Partition Key**: `username` (String) - The GitHub login of the user.
- **Attributes**: 
  - `teams` (List of Strings) - The list of teams the user belongs to.

## Multi-File PR Edge Case (Path-Restricted Approvals)

**Decision: Any Sensitive File Triggers Strict Rules**

Because Cedar's `like` operator evaluates a single string at a time, we had to decide how to handle Pull Requests that modify multiple files. 
We have explicitly decided that **if ANY file in the PR touches a sensitive path (e.g. `/auth/`), the entire PR is evaluated under the strict path-restricted policy.** 
The Lambda handler (`webhook_handler.py`) loops through the fetched files and aggressively forwards the first sensitive path it finds to Cedar. If no sensitive paths are found, it forwards the first file in the PR array. This guarantees secure-by-default behavior without complicating the Cedar schema.

*This decision is locked in. Any downstream integration (webhook parsing, AVP calls, Cedar policies) must adhere to this context-driven approach.*
