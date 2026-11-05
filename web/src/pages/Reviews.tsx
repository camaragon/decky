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

const EMPTY = {
  direct: "no review requests",
  team: "no team review requests",
  githubReview: "no review requests",
  githubTeam: "no team review requests",
};

export function ReviewsPage() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const useQueueSource = Boolean(meta.data?.queueConfigured);
  const queue = useQueue(useQueueSource);
  const review = useTable("review", !useQueueSource);
  const team = useTable("team", !useQueueSource);
  const config = useConfig();
  const hideAuthors = hideAuthorList(config.data?.settings);
  const [filters, setFilters] = useState<FilterState>(() => loadFilters("reviews-page"));

  useEffect(() => {
    saveFilters("reviews-page", filters);
  }, [filters]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "a") setFilters(defaultFilters());
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function refreshAll() {
    if (useQueueSource) queue.refetch();
    else {
      review.refetch();
      team.refetch();
    }
  }

  const jiraBrowseUrl = meta.data?.jiraBrowseUrl ?? null;

  if (useQueueSource && queueActive(queue.data)) {
    const today = queue.data.today;
    const direct = queue.data.direct.map((item) => queueToRow(item, true));
    const teamRows = queue.data.team.map((item) => queueToRow(item, true));
    return (
      <div>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h1 className="text-base font-semibold">Reviews</h1>
          <Button type="button" variant="outline" size="sm" onClick={refreshAll}>
            Refresh
          </Button>
        </div>
        <PrFilterBar filters={filters} onChange={setFilters} onReset={() => setFilters(defaultFilters())} />
        <PrSection
          title="Requested from me"
          rows={direct}
          hideAuthors={hideAuthors}
          filters={filters}
          empty={EMPTY.direct}
          reviewAction
          showReviewed
          queueMode
          jiraBrowseUrl={jiraBrowseUrl}
          queueToday={today}
        />
        <PrSection
          title="Via team"
          rows={teamRows}
          hideAuthors={hideAuthors}
          filters={filters}
          empty={EMPTY.team}
          reviewAction
          showReviewed
          queueMode
          jiraBrowseUrl={jiraBrowseUrl}
          queueToday={today}
        />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h1 className="text-base font-semibold">Reviews</h1>
        <Button type="button" variant="outline" size="sm" onClick={refreshAll}>
          Refresh
        </Button>
      </div>
      <PrFilterBar filters={filters} onChange={setFilters} onReset={() => setFilters(defaultFilters())} />
      <PrSection
        title="Review requests"
        rows={review.data?.rows ?? []}
        hideAuthors={hideAuthors}
        filters={filters}
        empty={EMPTY.githubReview}
        reviewAction
      />
      <PrSection
        title="Team review requests"
        rows={team.data?.rows ?? []}
        hideAuthors={hideAuthors}
        filters={filters}
        empty={EMPTY.githubTeam}
        reviewAction
      />
    </div>
  );
}
