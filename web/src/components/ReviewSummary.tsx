import type { ReviewResult, ReviewRisk } from "../lib/api";

const riskColors = {
  low: "border-emerald-600 text-emerald-700 dark:text-emerald-400",
  medium: "border-amber-600 text-amber-800 dark:text-amber-400",
  high: "border-red-500 bg-red-500/10 text-red-700 dark:text-red-400",
};

export function RiskLabel({ risk }: { risk: ReviewRisk }) {
  return <span className={`rounded border px-2 py-1 text-xs ${riskColors[risk]}`}>Risk: {risk}</span>;
}

export function ReviewSummary({ result }: { result: ReviewResult }) {
  return <section aria-label="Review summary" className="space-y-2">
    <h4 className="font-semibold">Review summary</h4>
    {result.outdated ? <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Outdated result — the PR head has changed. Review the latest diff before deciding.</p> : null}
    <p className="text-xs text-muted-foreground">Generated <time dateTime={result.generated_at}>{new Date(result.generated_at).toLocaleString()}</time></p>
    <div className={`grid gap-3 ${result.second_opinion ? "md:grid-cols-2" : ""}`}>
      <div className="min-w-0 space-y-2 rounded border border-border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><h5 className="min-w-0 flex-1 break-words font-medium">{result.reviewer}</h5><RiskLabel risk={result.risk} /></div>
        <dl className="space-y-2 break-words text-sm">
          <div><dt className="font-medium">What changed</dt><dd className="whitespace-pre-wrap">{result.summary.what_changed}</dd></div>
          <div><dt className="font-medium">Why</dt><dd className="whitespace-pre-wrap">{result.summary.why}</dd></div>
          <div><dt className="font-medium">What to check</dt><dd className="whitespace-pre-wrap">{result.summary.what_to_check}</dd></div>
        </dl>
      </div>
      {result.second_opinion ? <div className="min-w-0 space-y-2 rounded border border-border p-3">
        <p className="text-xs text-muted-foreground">Second opinion</p>
        <div className="flex flex-wrap items-center justify-between gap-2"><h5 className="min-w-0 flex-1 break-words font-medium">{result.second_opinion.reviewer}</h5><RiskLabel risk={result.second_opinion.risk} /></div>
        <p className="whitespace-pre-wrap break-words text-sm">{result.second_opinion.summary}</p>
      </div> : null}
    </div>
  </section>;
}
