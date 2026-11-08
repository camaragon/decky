import { ChevronDown, GitPullRequest } from "lucide-react";
import { useMemo, useState } from "react";

import type { InboxStack, PrRow } from "../lib/api";
import { postReview } from "../lib/api";
import { filterRows, type FilterState } from "../lib/filters";
import { formatRelativeTime } from "../lib/time";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";

type Props = {
  title: string;
  inboxStacks?: InboxStack[];
  rows: PrRow[];
  hideAuthors: string[];
  filters: FilterState;
  empty: string;
  showAuthor?: boolean;
  defaultOpen?: boolean;
  reviewAction?: boolean;
  showReviewed?: boolean;
  queueMode?: boolean;
  jiraBrowseUrl?: string | null;
  queueToday?: string;
};

function checkVariant(checks: string): "pass" | "fail" | "pending" | "none" {
  if (checks === "pass" || checks === "fail" || checks === "pending") return checks;
  return "none";
}

function jiraHref(template: string, key: string): string {
  return template.includes("{key}") ? template.replace("{key}", key) : `${template.replace(/\/$/, "")}/${key}`;
}

export function PrSection({
  title,
  inboxStacks,
  rows,
  hideAuthors,
  filters,
  empty,
  showAuthor = true,
  defaultOpen = true,
  reviewAction = false,
  showReviewed = false,
  queueMode = false,
  jiraBrowseUrl = null,
  queueToday = "",
}: Props) {
  const stackPositions = new Map(inboxStacks?.filter(s => s.prs.length > 1).flatMap(s =>
    s.prs.map((pr, index) => [`${pr.repo}#${pr.number}`, `${index + 1}/${s.prs.length} in stack`] as const)));
  const [open, setOpen] = useState(defaultOpen);
  const [message, setMessage] = useState<string | null>(null);
  const visible = useMemo(() => filterRows(rows, filters, hideAuthors), [rows, filters, hideAuthors]);

  async function runReview(row: PrRow) {
    setMessage(null);
    try {
      const res = await postReview(row.repo, row.number);
      setMessage(res.message);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "action failed");
    }
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-6">
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md py-1 text-left hover:bg-accent/50">
        <ChevronDown aria-hidden="true" className={cn("h-4 w-4 transition-transform", !open && "-rotate-90")} />
        <h2 className="text-sm font-semibold">
          {title} <span className="count">{visible.length}</span>
        </h2>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-1">
        {message ? <p className="mb-2 text-xs text-emerald-700 dark:text-emerald-300">{message}</p> : null}
        {visible.length === 0 ? (
          <p className="py-2 text-xs text-muted-foreground">{empty}</p>
        ) : (
          <ul className="pr-list">
            {visible.map((row) => (
              <PrRowLine
                key={`${row.repo}#${row.number}`}
                row={row}
                stackPosition={!showAuthor ? stackPositions.get(`${row.repo}#${row.number}`) : undefined}
                showAuthor={showAuthor}
                reviewAction={reviewAction}
                showReviewed={showReviewed}
                queueMode={queueMode}
                jiraBrowseUrl={jiraBrowseUrl}
                queueToday={queueToday}
                onReview={() => runReview(row)}
              />
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function PrRowLine({
  row,
  stackPosition,
  showAuthor,
  reviewAction,
  showReviewed,
  queueMode,
  jiraBrowseUrl,
  queueToday,
  onReview,
}: {
  row: PrRow;
  stackPosition?: string;
  showAuthor: boolean;
  reviewAction: boolean;
  showReviewed: boolean;
  queueMode: boolean;
  jiraBrowseUrl: string | null;
  queueToday: string;
  onReview: () => void;
}) {
  const relative = queueMode
    ? row.opened === queueToday
      ? "Today"
      : row.opened
    : formatRelativeTime(row.updated_at ?? "");
  return (
    <li className="pr-list-row">
      <GitPullRequest aria-hidden="true" size={18} className={`pr-row-icon check-${row.checks}`} />
      <div className="pr-row-main">
        <a href={row.url} target="_blank" rel="noreferrer" className="pr-row-title">{row.title}</a>
        <div className="pr-row-meta">
          <a href={row.url} target="_blank" rel="noreferrer">{row.repo}#{row.number}</a>
          {showAuthor ? <span>{row.author}</span> : null}
          {stackPosition ? <span className="stack-position">{stackPosition}</span> : null}
          {queueMode ? <span>opened {relative}</span> : <>
            {row.opened ? <span>opened {formatRelativeTime(row.opened)}</span> : null}
            <span>updated {relative || "unknown"}</span>
            {row.additions != null && row.deletions != null ? <span className="size-stat"><span className="check-pass">+{row.additions}</span> <span className="check-fail">−{row.deletions}</span></span> : null}
          </>}
          {row.jira?.map(key => jiraBrowseUrl ? <a key={key} href={jiraHref(jiraBrowseUrl, key)} target="_blank" rel="noreferrer">{key}</a> : <span key={key}>{key}</span>)}
        </div>
      </div>
      <div className="pr-row-status">
        {!queueMode ? <Badge variant={checkVariant(row.checks)}>Checks: {row.checks}</Badge> : null}
        {row.draft ? <Badge variant="draft">draft</Badge> : null}
        {!queueMode ? <span className={`fact ${row.review_decision === "CHANGES_REQUESTED" ? "check-fail" : row.review_decision === "APPROVED" ? "check-pass" : ""}`}>{row.review_decision?.replaceAll("_", " ").toLowerCase() || "No review decision"} · {row.approvals} approval{row.approvals === 1 ? "" : "s"}</span> : null}
        {showReviewed && row.reviewed != null ? <span className="fact">{row.reviewed ? "Reviewed" : "Not reviewed"}</span> : null}
      </div>
      <div className="pr-row-actions">
        {reviewAction ? <Button type="button" size="sm" onClick={onReview}>Review</Button> : null}
        <Button type="button" size="sm" variant="outline" asChild><a href={row.url} target="_blank" rel="noreferrer">Open ↗</a></Button>
      </div>
    </li>
  );
}

export { PrSection as PrTable };
