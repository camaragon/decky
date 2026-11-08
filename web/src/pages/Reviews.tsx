import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { QueryFeedback } from "../components/QueryFeedback";
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

  if (!meta.data) return <QueryFeedback label="settings" query={meta} />;

  const jiraBrowseUrl = meta.data?.jiraBrowseUrl ?? null;

  if (useQueueSource) {
    const today = queueActive(queue.data) ? queue.data.today : "";
    const direct = queueActive(queue.data)
      ? queue.data.direct.map((item) => queueToRow(item, true))
      : [];
    const teamRows = queueActive(queue.data)
      ? queue.data.team.map((item) => queueToRow(item, true))
      : [];
    return (
      <div>
        <div className="page-header">
          <div><h1>Reviews</h1><p>PRs waiting for your review, directly or via a team.</p></div>
          <Button type="button" variant="outline" size="sm" onClick={refreshAll}>
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
        <QueryFeedback label="queue" query={queue} />
        {queueActive(queue.data) ? (
          <>
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
          </>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div><h1>Reviews</h1><p>PRs waiting for your review, directly or via a team.</p></div>
        <Button type="button" variant="outline" size="sm" onClick={refreshAll}>
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
      <QueryFeedback label="review requests" query={review} />
      {review.data ? (
        <PrSection
          title="Review requests"
          rows={review.data?.rows ?? []}
          hideAuthors={hideAuthors}
          filters={filters}
          empty={EMPTY.githubReview}
          reviewAction
        />
      ) : null}
      <QueryFeedback label="team review requests" query={team} />
      {team.data ? (
        <PrSection
          title="Team review requests"
          rows={team.data?.rows ?? []}
          hideAuthors={hideAuthors}
          filters={filters}
          empty={EMPTY.githubTeam}
          reviewAction
        />
      ) : null}
    </div>
  );
}
