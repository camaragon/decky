import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { QueryFeedback } from "../components/QueryFeedback";
import { PrFilterBar } from "../components/PrFilterBar";
import { PrSection } from "../components/PrSection";
import { Button } from "../components/ui/button";
import { hideAuthorList, useConfig } from "../hooks/useConfig";
import { queueActive, useQueue } from "../hooks/useQueue";
import { useTable } from "../hooks/useTables";
import { fetchInbox, fetchMeta } from "../lib/api";
import { defaultFilters, loadFilters, saveFilters, type FilterState } from "../lib/filters";
import { queueToRow } from "../lib/queue";

export function MyPrsPage() {
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: fetchInbox, enabled: false });
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

  if (!meta.data) return <QueryFeedback label="settings" query={meta} />;

  const jiraBrowseUrl = meta.data?.jiraBrowseUrl ?? null;
  const rows =
    useQueueSource && queueActive(queue.data)
      ? queue.data.mine.map((item) => queueToRow(item, false))
      : useQueueSource
        ? []
        : (mine.data?.rows ?? []);

  return (
    <div>
      <div className="page-header">
        <div><h1>My PRs</h1><p>Your open PRs and what they are waiting on.</p></div>
        <Button type="button" variant="outline" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>
      <QueryFeedback label="settings" query={meta} />
      <QueryFeedback label="config" query={config} />
      <PrFilterBar
        filters={filters}
        onChange={setFilters}
        onReset={() => setFilters(defaultFilters())}
      />
      <QueryFeedback
        label={useQueueSource ? "queue" : "my PRs"}
        query={useQueueSource ? queue : mine}
      />
      {(useQueueSource ? queueActive(queue.data) : Boolean(mine.data)) ? (
        <PrSection
          title="My PRs"
          rows={rows}
          inboxStacks={inbox.data?.stacks}
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
