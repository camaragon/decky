import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import type { PrRow } from "../lib/api";
import { postReview } from "../lib/api";
import { filterRows, type FilterState } from "../lib/filters";
import { formatRelativeTime } from "../lib/time";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";

type Props = {
  title: string;
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
        <ChevronDown className={cn("h-4 w-4 transition-transform", !open && "-rotate-90")} />
        <h2 className="text-sm font-semibold">
          {title} {visible.length}
        </h2>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-1">
        {message ? <p className="mb-2 text-xs text-emerald-700 dark:text-emerald-300">{message}</p> : null}
        {visible.length === 0 ? (
          <p className="py-2 text-xs text-muted-foreground">{empty}</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <tbody>
                {visible.map((row) => (
                  <PrRowLine
                    key={`${row.repo}#${row.number}`}
                    row={row}
                    showAuthor={showAuthor}
                    reviewAction={reviewAction}
                    showReviewed={showReviewed}
                    queueMode={queueMode}
                    jiraBrowseUrl={jiraBrowseUrl}
                    queueToday={queueToday}
                    onReview={() => runReview(row)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function PrRowLine({
  row,
  showAuthor,
  reviewAction,
  showReviewed,
  queueMode,
  jiraBrowseUrl,
  queueToday,
  onReview,
}: {
  row: PrRow;
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
    <tr className="group border-b border-border last:border-0 hover:bg-muted/40">
      <td className="w-[1%] whitespace-nowrap px-2 py-1.5 align-middle">
        <a
          href={row.url}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-primary hover:underline"
        >
          {row.repo}#{row.number}
        </a>
      </td>
      <td className="max-w-md truncate px-2 py-1.5 align-middle" title={row.title}>
        {row.title}
      </td>
      {showAuthor ? (
        <td className="whitespace-nowrap px-2 py-1.5 align-middle text-muted-foreground">{row.author}</td>
      ) : null}
      {!queueMode ? (
        <td className="whitespace-nowrap px-2 py-1.5 align-middle">
          <Badge variant={checkVariant(row.checks)}>{row.checks}</Badge>
        </td>
      ) : null}
      <td className="whitespace-nowrap px-2 py-1.5 align-middle">
        {row.draft ? <Badge variant="draft">draft</Badge> : null}
      </td>
      {showReviewed ? (
        <td className="whitespace-nowrap px-2 py-1.5 align-middle">
          {row.reviewed === true ? (
            <span title="Reviewed">✓</span>
          ) : row.reviewed === false ? (
            <span title="Not reviewed">·</span>
          ) : null}
        </td>
      ) : null}
      {!queueMode ? (
        <td className="whitespace-nowrap px-2 py-1.5 align-middle tabular-nums">{row.approvals}</td>
      ) : null}
      <td className="whitespace-nowrap px-2 py-1.5 align-middle text-muted-foreground">{relative ?? ""}</td>
      <td className="max-w-[10rem] truncate px-2 py-1.5 align-middle">
        {row.jira?.length ? (
          row.jira.map((key, i) => (
            <span key={key}>
              {i > 0 ? ", " : null}
              {jiraBrowseUrl ? (
                <a href={jiraHref(jiraBrowseUrl, key)} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  {key}
                </a>
              ) : (
                key
              )}
            </span>
          ))
        ) : (
          "—"
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 align-middle">
        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          {reviewAction ? (
            <Button type="button" size="sm" onClick={onReview}>
              Review
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="outline" asChild>
            <a href={row.url} target="_blank" rel="noreferrer">
              Open
            </a>
          </Button>
        </div>
      </td>
    </tr>
  );
}

export { PrSection as PrTable };
