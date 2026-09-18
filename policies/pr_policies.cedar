// Core Authorization Rules for GitHub PRs

// Rule 1: Security team owns authentication modifications
permit (
  principal,
  action in [CedarGatekeeper::Action::"approvePR", CedarGatekeeper::Action::"mergePR"],
  resource
)
when { context.activeTeams.contains("security-team") && context.changedPath like "/src/auth/*" };

// Rule 2: Strict ban on self-approvals and self-merges
forbid (
  principal,
  action in [CedarGatekeeper::Action::"approvePR", CedarGatekeeper::Action::"mergePR"],
  resource
)
when { context.prAuthor == principal };

// Rule 3: General engineers can approve and merge non-auth PRs
permit (
  principal,
  action in [CedarGatekeeper::Action::"approvePR", CedarGatekeeper::Action::"mergePR"],
  resource
)
when { 
  (context.activeTeams.contains("engineering-core") || context.activeTeams.contains("senior-engineers")) && 
  !(context.changedPath like "/src/auth/*") 
};

// Rule 4: Large PRs require senior engineering approval
forbid (
  principal,
  action in [CedarGatekeeper::Action::"approvePR", CedarGatekeeper::Action::"mergePR"],
  resource
)
when {
  context.totalLinesChanged > 500 &&
  !(context.activeTeams.contains("senior-engineers"))
};
