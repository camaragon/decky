import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { fetchInbox, sendAnswer, type InboxPr, type InboxStack } from "../lib/api";
import { Button } from "../components/ui/button";

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
  return <div className="space-y-2">
    <label className="block text-sm">Optional note for {scope === "stack" ? "whole stack" : `PR #${stack.prs[0].number}`}
      <textarea name="note" autoComplete="off" maxLength={10000} className="mt-1 block min-h-16 w-full rounded border border-border bg-background p-2" value={note} onChange={e => setNote(e.target.value)} />
    </label>
    <div className="flex flex-wrap gap-2">
      <Button className="min-h-11 flex-1" disabled={!enabled || pending} onClick={() => answer("merge")}>Merge{scope === "stack" ? " stack" : ""}</Button>
      <Button className="min-h-11 flex-1" variant="outline" disabled={!enabled || pending} onClick={() => answer("hold")}>Hold{scope === "stack" ? " stack" : ""}</Button>
    </div>
    {!enabled ? <p className="text-sm text-muted-foreground">Configure review.decision_command to send answers.</p> : null}
    <p role="status" className="text-sm">{pending ? "Sending answer…" : message}</p>
  </div>;
}

export function InboxPage() {
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: fetchInbox, staleTime: 60000, refetchOnWindowFocus: false, retry: false });
  const [answers, setAnswers] = useState(savedAnswers);
  function remember(prs: InboxPr[], answer: string) {
    setAnswers(previous => {
      const next = { ...previous };
      for (const pr of prs) next[answerKey(pr)] = answer;
      try { sessionStorage.setItem("decky.inbox.answers.v1", JSON.stringify(next)); } catch { /* Session memory still works when storage is unavailable. */ }
      return next;
    });
  }
  return <div className="inbox w-full min-w-0 space-y-4">
    <div className="flex items-center justify-between gap-2"><h1 className="text-xl font-semibold">Review inbox</h1>
      <Button variant="outline" className="min-h-11" disabled={inbox.isFetching} onClick={() => inbox.refetch()}>Refresh</Button></div>
    <p className="text-sm text-muted-foreground">Your open PRs, in merge order. Answers go to your configured command.</p>
    {inbox.isFetching ? <p role="status">Loading PRs…</p> : null}
    {inbox.error ? <p role="alert">{inbox.error.message}</p> : null}
    {inbox.data && !inbox.data.all_owners && !inbox.data.owners.length ? <p>Configure review.owners to see your open PRs. No GitHub queries were made.</p> : null}
    {inbox.data && (inbox.data.all_owners || inbox.data.owners.length > 0) && !inbox.data.stacks.length ? <p>{inbox.data.all_owners ? "No open PRs were found." : "No open PRs in your configured owners."}</p> : null}
    {inbox.data?.notes.map(note => <p key={note} className="text-sm">{note}</p>)}
    {inbox.data?.stacks.map((stack, index, all) => <section key={`${stack.repo}:${stack.prs[0].number}`}>
      {index === 0 || all[index - 1].repo !== stack.repo ? <h2 className="mb-2 break-words text-lg font-semibold">{stack.repo}</h2> : null}
      <details className="group/stack rounded-lg border border-border bg-card">
        <summary className="flex cursor-pointer flex-wrap items-center gap-2 rounded-lg p-3 font-medium hover:bg-accent [&::-webkit-details-marker]:hidden">
          <ChevronRight aria-hidden="true" className="size-4 shrink-0 group-open/stack:rotate-90" />
          <span className="min-w-0 flex-1 basis-[calc(100%-1.5rem)] sm:basis-64">{stack.prs.length === 1 ? "Single PR" : `${stack.prs.length} PR stack`} · #{stack.prs[0].number} {stack.prs[0].title}</span>
          <span className="flex w-full flex-wrap gap-2 pl-6 text-xs sm:w-auto sm:pl-0">
            {stack.prs.some(pr => pr.checks === "fail") ? <span className="rounded border border-red-500 bg-red-500/10 px-2 py-1 text-red-700 dark:text-red-400">Checks fail: {stack.prs.filter(pr => pr.checks === "fail").length}</span> : null}
            {stack.prs.some(pr => pr.review_decision === "CHANGES_REQUESTED") ? <span className="rounded border border-red-500 bg-red-500/10 px-2 py-1 text-red-700 dark:text-red-400">Changes requested: {stack.prs.filter(pr => pr.review_decision === "CHANGES_REQUESTED").length}</span> : null}
            {stack.prs.some(pr => pr.checks === "pending") ? <span className="rounded border border-border px-2 py-1 text-amber-700 dark:text-amber-400">Checks pending: {stack.prs.filter(pr => pr.checks === "pending").length}</span> : null}
          </span>
        </summary>
        <div className="space-y-4 p-3 pt-0">
          {stack.prs.map((pr, order) => <details key={pr.number} className="group/pr rounded-md border border-border">
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 rounded-md p-3 hover:bg-accent [&::-webkit-details-marker]:hidden">
              <ChevronRight aria-hidden="true" className="size-4 shrink-0 group-open/pr:rotate-90" />
              <h3 className="min-w-0 flex-1 basis-[calc(100%-1.5rem)] font-semibold sm:basis-64">{order + 1}. #{pr.number} {pr.title}</h3>
              <span className="flex w-full flex-wrap gap-2 pl-6 text-xs sm:w-auto sm:pl-0">
                <span className={`rounded border px-2 py-1 ${pr.checks === "fail" ? "border-red-500 bg-red-500/10 text-red-700 dark:text-red-400" : pr.checks === "pending" ? "border-border text-amber-700 dark:text-amber-400" : "border-border text-muted-foreground"}`}>Checks: {pr.checks}</span>
                <span className={`rounded border px-2 py-1 ${pr.review_decision === "CHANGES_REQUESTED" ? "border-red-500 bg-red-500/10 text-red-700 dark:text-red-400" : "border-border text-muted-foreground"}`}>{pr.review_decision?.replaceAll("_", " ") || "No review decision"}</span>
                {pr.draft ? <span className="rounded border border-border px-2 py-1 text-muted-foreground">Draft</span> : null}
                {answers[answerKey(pr)] ? <span className="rounded border border-border px-2 py-1 text-muted-foreground">Answered: {answers[answerKey(pr)].split(":")[0]}</span> : null}
              </span>
            </summary>
            <div className="space-y-3 p-3 pt-0">
              <p className="whitespace-pre-wrap text-sm">{summary(pr.body)}</p>
              <details><summary className="cursor-pointer">Full description</summary><p className="whitespace-pre-wrap text-sm">{plain(pr.body) || "No description provided."}</p></details>
              <details><summary className="cursor-pointer">{pr.changed_files} files changed · +{pr.files.reduce((n, f) => n + f.additions, 0)} / −{pr.files.reduce((n, f) => n + f.deletions, 0)}</summary>
                <ul className="space-y-2 text-sm">{pr.files.map(file => <li key={file.path}>{file.path} <span className="whitespace-nowrap">+{file.additions} / −{file.deletions}</span></li>)}</ul></details>
              <div className="grid grid-cols-2 gap-2">{pr.image_urls.map((url, i) => {
                const src = `/api/inbox/image?${new URLSearchParams({ repo: pr.repo, number: String(pr.number), url })}`;
                return <a key={url} href={src} target="_blank" rel="noreferrer"><img src={src} alt={`PR #${pr.number} screenshot ${i + 1}`} loading="lazy" className="h-28 w-full rounded border border-border object-contain" /></a>;
              })}</div>
              <div className="flex flex-wrap gap-3 text-sm"><a href={pr.url} target="_blank" rel="noreferrer">Open PR ↗</a><a href={`${pr.url}/files`} target="_blank" rel="noreferrer">Files changed ↗</a></div>
              {answers[answerKey(pr)] ? <p className="text-sm">Last answer: {answers[answerKey(pr)]}</p> : null}
              <AnswerForm stack={{ repo: stack.repo, prs: [pr] }} scope="pr" enabled={Boolean(inbox.data?.decision_enabled)} onAnswered={remember} />
            </div>
          </details>)}
          <AnswerForm stack={stack} scope="stack" enabled={Boolean(inbox.data?.decision_enabled)} onAnswered={remember} />
        </div>
      </details>
    </section>)}
  </div>;
}
