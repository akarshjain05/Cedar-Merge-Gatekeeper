// Core Authorization Rules for GitHub PRs

// Rule 1: Security team owns authentication modifications
permit (
  principal,
  action in [Action::"approvePR", Action::"mergePR"],
  resource
)
when { context.activeTeams.contains("security-team") && context.changedPath like "/src/auth/*" };

// Rule 2: Strict ban on self-approvals
forbid (
  principal,
  action == Action::"approvePR",
  resource
)
when { context.prAuthor == principal };

// Rule 3: General engineers can approve and merge non-auth PRs
permit (
  principal,
  action in [Action::"approvePR", Action::"mergePR"],
  resource
)
when { 
  context.activeTeams.contains("engineering-core") && 
  !(context.changedPath like "/src/auth/*") 
};

// Rule 4: Large PRs require senior engineering approval
forbid (
  principal,
  action == Action::"approvePR",
  resource
)
when {
  context.totalLinesChanged > 500 &&
  !(context.activeTeams.contains("senior-engineers"))
};
