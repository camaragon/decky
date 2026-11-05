import type { PrRow, QueuePr } from "./api";
import { queueItemRepo } from "./repo";

export function queueToRow(item: QueuePr, forReview: boolean): PrRow {
  return {
    number: item.number,
    repo: queueItemRepo(item),
    title: item.title,
    author: item.author,
    checks: forReview && !item.draft ? "pass" : item.draft ? "none" : "pass",
    approvals: 0,
    draft: item.draft,
    url: item.url,
    opened: item.opened,
    jira: item.jira,
    reviewed: item.reviewed,
  };
}
