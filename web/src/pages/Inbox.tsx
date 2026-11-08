import { useQuery } from "@tanstack/react-query";
import { useState, type KeyboardEvent } from "react";
import { ExternalLink, MessageSquare, RefreshCw } from "lucide-react";

import { fetchInbox, sendAnswer, type InboxPr, type InboxStack } from "../lib/api";
import { triageGroup } from "../lib/triage";
import { formatRelativeTime } from "../lib/time";
import { Button } from "../components/ui/button";
import { ReviewSummary, RiskLabel } from "../components/ReviewSummary";

function plain(text: string) {
  return text.replace(/<[^>]*>/g, "").replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/^[#>]+\s*/gm, "").replace(/[*_`]/g, "").trim();
}
function summary(body: string) {
  const section = body.match(/^#{1,6}\s+(?:what(?: changed)?|summary)\s*\r?\n([\s\S]*?)(?=^#{1,6}\s|$(?![\s\S]))/im);
  return plain(section?.[1]?.trim() || body.trim().split(/\r?\n\s*\r?\n/)[0] || "No description provided.");
}
const answerKey = (pr: InboxPr) => `${pr.repo}#${pr.number}@${pr.head_sha}`;
function savedAnswers(): Record<string, string> {
  try { return JSON.parse(sessionStorage.getItem("decky.inbox.answers.v1") || "{}"); }
  catch { return {}; }
}

function AnswerForm({ stack, scope, enabled, onAnswered }: {
  stack: InboxStack; scope: "pr" | "stack"; enabled: boolean;
  onAnswered: (prs: InboxPr[], answer: string) => void;
}) {
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  async function answer(decision: "merge" | "hold") {
    setPending(true); setMessage("");
    try {
      const result = await sendAnswer(stack, scope, decision, note);
      onAnswered(stack.prs, `${decision === "merge" ? "Merge" : "Hold"}${note ? `: ${note}` : ""}`);
      setMessage(result.message); setNote("");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not deliver answer"); }
    finally { setPending(false); }
  }
  return <div className="answer-form">
    <div className="answer-buttons">
      <Button data-answer="m" data-confirm={scope === "stack" ? `Merge all ${stack.prs.length} PRs?` : undefined} disabled={!enabled || pending} onClick={() => answer("merge")}>{scope === "stack" ? `Merge all ${stack.prs.length}` : "Merge"}{note ? " with note" : ""} <kbd>M</kbd></Button>
      <Button data-answer="h" data-confirm={scope === "stack" ? `Hold all ${stack.prs.length} PRs?` : undefined} variant="outline" disabled={!enabled || pending} onClick={() => answer("hold")}>Hold{scope === "stack" ? " stack" : ""}{note ? " with note" : ""} <kbd>H</kbd></Button>
      <Button data-answer="n" variant="ghost" aria-label="Add a note" aria-expanded={showNote} onClick={() => setShowNote(!showNote)}><MessageSquare aria-hidden="true" size={15} /><kbd>N</kbd></Button>
    </div>
    {showNote ? <label className="note-bar">Optional note for {scope === "stack" ? "whole stack" : `PR #${stack.prs[0].number}`}
      <input autoFocus name="note" autoComplete="off" maxLength={10000} value={note} onChange={e => setNote(e.target.value)} />
    </label> : null}
    {!enabled ? <p className="text-xs text-muted-foreground">Configure review.decision_command to send answers.</p> : null}
    {pending || message ? <p role="status" className="text-sm">{pending ? "Sending answer…" : message}</p> : null}
  </div>;
}

function PrContext({ pr }: { pr: InboxPr }) {
  const runs = pr.check_runs ?? [];
  const statuses = (pr.commit_statuses ?? []).filter((status, index, all) => all.findIndex(s => s.name === status.name) === index);
  const passed = runs.filter(c => ["success", "neutral", "skipped"].includes(c.conclusion ?? "")).length + statuses.filter(c => c.state === "success").length;
  const failed = [...runs.filter(c => ["failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"].includes(c.conclusion ?? "")), ...statuses.filter(c => ["failure", "error"].includes(c.state))];
  const count = runs.length + statuses.length;
  return <>
    <div className="pr-facts">
      {pr.review_result ? <RiskLabel risk={pr.review_result.risk} /> : <span className="fact">No review yet</span>}
      {pr.review_result?.outdated ? <span className="fact check-pending">Outdated result</span> : null}
      <span className={`fact check-${pr.checks}`}>Checks {count ? `${passed}/${count}` : pr.checks === "none" ? "none" : pr.checks}</span>
      <span className={`fact ${pr.review_decision === "CHANGES_REQUESTED" ? "check-fail" : pr.review_decision === "APPROVED" ? "check-pass" : ""}`}>{pr.review_decision?.replaceAll("_", " ").toLowerCase() || "No review decision"}{pr.approvals ? ` · ${pr.approvals} approval${pr.approvals === 1 ? "" : "s"}` : ""}</span>
      {pr.draft ? <span className="fact">Draft</span> : null}
      <span className="size-stat"><span className="check-pass">+{pr.additions ?? pr.files.reduce((n, f) => n + f.additions, 0)}</span> <span className="check-fail">−{pr.deletions ?? pr.files.reduce((n, f) => n + f.deletions, 0)}</span> · {pr.changed_files} files</span>
      <span className="text-xs text-muted-foreground">opened {formatRelativeTime(pr.opened ?? "") || "unknown"} · updated {formatRelativeTime(pr.updated_at ?? "") || "unknown"}</span>
    </div>
    {failed.length ? <p className="text-sm check-fail">Failing: {failed.map((check, i) => <span key={check.name}>{i ? ", " : ""}{check.url ? <a href={check.url} target="_blank" rel="noreferrer">{check.name}</a> : check.name}</span>)}</p> : null}
    <p className="pr-summary">{pr.review_result?.summary.what_changed || summary(pr.body)}</p>
  </>;
}

function PrDetails({ pr }: { pr: InboxPr }) {
  return <details className="pr-details"><summary>Why · what to check · {pr.changed_files} files{pr.image_urls.length ? ` · ${pr.image_urls.length} screenshots` : ""}</summary>
    <div className="space-y-3 pt-3">
      {pr.review_result ? <ReviewSummary result={pr.review_result} /> : null}
      <details><summary>Full description</summary><p className="whitespace-pre-wrap text-sm">{plain(pr.body) || "No description provided."}</p></details>
      <ul className="space-y-2 text-sm">{pr.files.map(file => <li key={file.path}>{file.path} <span className="size-stat">+{file.additions} / −{file.deletions}</span></li>)}</ul>
      <a href={`${pr.url}/files`} target="_blank" rel="noreferrer">All files on GitHub ↗</a>
      <div className="grid grid-cols-2 gap-2">{pr.image_urls.map((url, i) => {
        const src = `/api/inbox/image?${new URLSearchParams({ repo: pr.repo, number: String(pr.number), url })}`;
        return <a key={url} href={src} target="_blank" rel="noreferrer"><img src={src} alt={`PR #${pr.number} screenshot ${i + 1}`} width={320} height={180} loading="lazy" className="h-28 w-full rounded border border-border object-contain" /></a>;
      })}</div>
    </div>
  </details>;
}

export function InboxPage() {
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: fetchInbox, staleTime: 60000, refetchOnWindowFocus: false, retry: false });
  const [answers, setAnswers] = useState(savedAnswers);
  const [filter, setFilter] = useState("All");
  function remember(prs: InboxPr[], answer: string) {
    setAnswers(previous => {
      const next = { ...previous };
      for (const pr of prs) next[answerKey(pr)] = answer;
      try { sessionStorage.setItem("decky.inbox.answers.v1", JSON.stringify(next)); } catch { /* Session memory still works when storage is unavailable. */ }
      return next;
    });
  }
  function keyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || (event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable]"))) return;
    const card = (event.target as HTMLElement).closest<HTMLElement>("[data-focus-card]");
    if (!card) return;
    const key = event.key.toLowerCase();
    if (key === "j" || key === "k") {
      const cards = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[data-focus-card]"));
      cards[(cards.indexOf(card) + (key === "j" ? 1 : cards.length - 1)) % cards.length]?.focus();
    } else if (["m", "h", "n"].includes(key)) {
      const button = ((event.target as HTMLElement).closest(".answer-form, .stack-rail > li") ?? card).querySelector<HTMLButtonElement>(`[data-answer="${key}"]`);
      if (button?.dataset.confirm && !button.disabled && !window.confirm(button.dataset.confirm)) {
        event.preventDefault();
        return;
      }
      const details = button?.closest("details");
      if (details) details.open = true;
      button?.click();
    } else return;
    event.preventDefault();
  }
  const groups = ["Needs attention", "Ready to decide", "Not ready"];
  const resultsEnabled = Boolean(inbox.data?.review_results_enabled);
  const stacks = [...(inbox.data?.stacks ?? [])].sort((a, b) => {
    const risk = (s: InboxStack) => Math.max(...s.prs.map(p => Math.max(({ low: 1, medium: 2, high: 3 })[p.review_result?.risk ?? "low"], ({ low: 1, medium: 2, high: 3 })[p.review_result?.second_opinion?.risk ?? "low"]) * 10 + (p.checks === "fail" ? 2 : 0) + (p.review_decision === "CHANGES_REQUESTED" ? 1 : 0)));
    return risk(b) - risk(a);
  });
  function form(stack: InboxStack, scope: "pr" | "stack") {
    return <AnswerForm stack={stack} scope={scope} enabled={Boolean(inbox.data?.decision_enabled)} onAnswered={remember} />;
  }
  function prContent(pr: InboxPr) {
    return <><div className="pr-identity"><span className="author-avatar" aria-label={`Author ${pr.author}`}>{pr.author?.slice(0, 2).toUpperCase() || "?"}</span><span>{pr.author} · {pr.repo}</span><a href={pr.url} target="_blank" rel="noreferrer">#{pr.number} <ExternalLink aria-hidden="true" size={12} /></a></div>
      <h3 className="pr-title">{pr.title}</h3><PrContext pr={pr} />
      {answers[answerKey(pr)] ? <p className="text-xs text-muted-foreground">Last answer: {answers[answerKey(pr)]}</p> : null}
      <PrDetails pr={pr} /></>;
  }
  return <div className="inbox space-y-5" onKeyDown={keyboard}>
    <header className="page-header"><div><h1>Inbox</h1><p>Your open PRs, worst first. Answers go to your configured command.</p></div><Button variant="outline" disabled={inbox.isFetching} onClick={() => inbox.refetch()}><RefreshCw aria-hidden="true" size={14} />Refresh</Button></header>
    <p className="keyboard-hints"><kbd>J</kbd> / <kbd>K</kbd> focus · <kbd>M</kbd> merge · <kbd>H</kbd> hold · <kbd>N</kbd> note</p>
    {inbox.isFetching ? <p role="status">Loading PRs…</p> : null}
    {inbox.error ? <p role="alert">{inbox.error.message}{inbox.data ? " — showing previous data" : ""}</p> : null}
    {inbox.data && !inbox.data.all_owners && !inbox.data.owners.length ? <p>Configure review.owners to see your open PRs. No GitHub queries were made.</p> : null}
    {inbox.data && (inbox.data.all_owners || inbox.data.owners.length > 0) && !inbox.data.stacks.length ? <p>{inbox.data.all_owners ? "No open PRs were found." : "No open PRs in your configured owners."}</p> : null}
    {inbox.data?.notes.map(note => <p key={note} className="text-sm">{note}</p>)}
    <div className="triage-filters" aria-label="Triage filters">{["All", ...groups].map(group => <button key={group} aria-pressed={filter === group} onClick={() => setFilter(group)}>{group} <span className="count">{stacks.filter(s => group === "All" || triageGroup(s, resultsEnabled) === group).reduce((n, s) => n + s.prs.length, 0)}</span></button>)}</div>
    {groups.filter(group => filter === "All" || filter === group).map(group => {
      const items = stacks.filter(s => triageGroup(s, resultsEnabled) === group);
      return items.length ? <section key={group} className="space-y-3"><h2 className="triage-heading">{group} <span className="count">{items.reduce((n, s) => n + s.prs.length, 0)}</span></h2>
        {items.map(stack => <article key={`${stack.repo}:${stack.prs[0].number}`} data-focus-card tabIndex={0} aria-label={stack.prs.length > 1 ? `${stack.prs.length} PR stack` : stack.prs[0].title} className={`triage-card ${stack.prs.length > 1 ? "stack-card" : ""}`}>
          {stack.prs.length === 1 ? <>{form(stack, "pr")}{prContent(stack.prs[0])}</> : <>
            <div className="stack-header"><div><h3>Stack of {stack.prs.length} <span className="text-muted-foreground font-normal">· {stack.repo}</span></h3><div className="pr-facts">{(() => {
              const risks = stack.prs.flatMap(p => p.review_result ? [p.review_result.risk] : []);
              return risks.length ? <RiskLabel risk={risks.includes("high") ? "high" : risks.includes("medium") ? "medium" : "low"} /> : <span className="fact">No review yet</span>;
            })()}<span className="fact">Checks {stack.prs.filter(p => p.checks === "pass").length}/{stack.prs.length} PRs</span><span className="fact">{stack.prs.filter(p => p.review_decision === "APPROVED").length}/{stack.prs.length} approved</span></div></div>{form(stack, "stack")}</div>
            <ol className="stack-rail">{stack.prs.map((pr, index) => <li key={pr.number}><span className="stack-number">{index + 1}</span>{prContent(pr)}<details className="pr-details"><summary>Answer only this PR</summary>{form({ repo: stack.repo, prs: [pr] }, "pr")}</details></li>)}</ol>
            <p className="text-xs text-muted-foreground">Merge order: {stack.prs.map(p => `#${p.number}`).join(" → ")}</p>
          </>}
        </article>)}
      </section> : null;
    })}
  </div>;
}
