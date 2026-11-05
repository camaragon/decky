import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router";

import { Layout } from "./components/Layout";
import { hideAuthorList, useConfig } from "./hooks/useConfig";
import { queueActive, useQueue } from "./hooks/useQueue";
import { useTable } from "./hooks/useTables";
import { fetchMeta } from "./lib/api";
import { filterRows, loadFilters } from "./lib/filters";
import { queueToRow } from "./lib/queue";
import { ConfigPage } from "./pages/Config";
import { MyPrsPage } from "./pages/MyPrs";
import { ReviewsPage } from "./pages/Reviews";

function Hotkeys() {
  const navigate = useNavigate();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "t") {
        const order = ["/", "/prs", "/config"];
        const idx = order.indexOf(window.location.pathname);
        navigate(order[(idx + 1) % order.length]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);
  return null;
}

function Shell() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const useQueueSource = Boolean(meta.data?.queueConfigured);
  const queue = useQueue(useQueueSource);
  const config = useConfig();
  const review = useTable("review", !useQueueSource);
  const team = useTable("team", !useQueueSource);
  const mine = useTable("mine", !useQueueSource);
  const hideAuthors = hideAuthorList(config.data?.settings);
  const reviewFilters = loadFilters("reviews-page");
  const mineFilters = loadFilters("mine-page");

  let reviewCount = 0;
  let mineCount = 0;
  if (useQueueSource && queueActive(queue.data)) {
    const direct = queue.data.direct.map((item) => queueToRow(item, true));
    const teamRows = queue.data.team.map((item) => queueToRow(item, true));
    const mineRows = queue.data.mine.map((item) => queueToRow(item, false));
    reviewCount =
      filterRows(direct, reviewFilters, hideAuthors).length +
      filterRows(teamRows, reviewFilters, hideAuthors).length;
    mineCount = filterRows(mineRows, mineFilters, hideAuthors).length;
  } else if (!useQueueSource) {
    reviewCount =
      filterRows(review.data?.rows ?? [], reviewFilters, hideAuthors).length +
      filterRows(team.data?.rows ?? [], reviewFilters, hideAuthors).length;
    mineCount = filterRows(mine.data?.rows ?? [], mineFilters, hideAuthors).length;
  }

  return (
    <>
      <Hotkeys />
      <Layout reviewCount={reviewCount} mineCount={mineCount}>
        <Routes>
          <Route path="/" element={<ReviewsPage />} />
          <Route path="/prs" element={<MyPrsPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
