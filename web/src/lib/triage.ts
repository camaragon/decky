import type { InboxPr, InboxStack } from "./api";

export function needsAttention(pr: InboxPr) {
  return pr.checks === "fail" || pr.review_decision === "CHANGES_REQUESTED" ||
    pr.review_result?.risk === "high" || pr.review_result?.second_opinion?.risk === "high" || Boolean(pr.review_result?.outdated);
}

export function triageGroup(stack: InboxStack) {
  if (stack.prs.some(needsAttention)) return "Needs attention";
  if (stack.prs.some(pr => pr.draft || pr.checks === "pending")) return "Not ready";
  return "Ready to decide";
}
