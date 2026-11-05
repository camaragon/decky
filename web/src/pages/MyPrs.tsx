import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PrFilterBar } from "../components/PrFilterBar";
import { PrSection } from "../components/PrSection";
import { Button } from "../components/ui/button";
import { hideAuthorList, useConfig } from "../hooks/useConfig";
import { queueActive, useQueue } from "../hooks/useQueue";
import { useTable } from "../hooks/useTables";
import { fetchMeta } from "../lib/api";
import { defaultFilters, loadFilters, saveFilters, type FilterState } from "../lib/filters";
import { queueToRow } from "../lib/queue";

export function MyPrsPage() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const useQueueSource = Boolean(meta.data?.queueConfigured);
  const queue = useQueue(useQueueSource);
  const mine = useTable("mine", !useQueueSource);
  const config = useConfig();
  const hideAuthors = hideAuthorList(config.data?.settings);
  const [filters, setFilters] = useState<FilterState>(() => loadFilters("mine-page"));

  useEffect(() => {
    saveFilters("mine-page", filters);
  }, [filters]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "a") setFilters(defaultFilters());
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function refresh() {
    if (useQueueSource) queue.refetch();
    else mine.refetch();
  }

  const jiraBrowseUrl = meta.data?.jiraBrowseUrl ?? null;
  const rows =
    useQueueSource && queueActive(queue.data)
      ? queue.data.mine.map((item) => queueToRow(item, false))
      : useQueueSource
        ? []
        : (mine.data?.rows ?? []);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h1 className="text-base font-semibold">My PRs</h1>
        <Button type="button" variant="outline" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>
      <PrFilterBar filters={filters} onChange={setFilters} onReset={() => setFilters(defaultFilters())} />
      {useQueueSource && queue.isLoading && !queueActive(queue.data) ? (
        <p className="py-2 text-xs text-muted-foreground">Loading queue…</p>
      ) : null}
      {useQueueSource && queue.error ? (
        <p className="py-2 text-xs text-red-600 dark:text-red-400">{String(queue.error)}</p>
      ) : null}
      {!useQueueSource || queueActive(queue.data) || queue.error ? (
        <PrSection
          title="My PRs"
          rows={rows}
          hideAuthors={hideAuthors}
          filters={filters}
          empty="no open PRs by you"
          showAuthor={false}
          queueMode={useQueueSource}
          jiraBrowseUrl={jiraBrowseUrl}
          queueToday={queueActive(queue.data) ? queue.data.today : ""}
        />
      ) : null}
    </div>
  );
}
