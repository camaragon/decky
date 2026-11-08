import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";

import { Layout } from "./components/Layout";
import { hideAuthorList, useConfig } from "./hooks/useConfig";
import { queueActive, useQueue } from "./hooks/useQueue";
import { useTable } from "./hooks/useTables";
import { fetchInbox, fetchMeta } from "./lib/api";
import { filterRows, loadFilters } from "./lib/filters";
import { needsAttention } from "./lib/triage";
import { queueToRow } from "./lib/queue";
import { ConfigPage } from "./pages/Config";
import { InboxPage } from "./pages/Inbox";
import { MyPrsPage } from "./pages/MyPrs";
import { ReviewsPage } from "./pages/Reviews";

function Hotkeys() {
  const navigate = useNavigate();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.altKey || e.ctrlKey || e.metaKey || (e.target instanceof HTMLElement && e.target.closest("input, select, textarea, [contenteditable]"))) return;
      if (e.key === "t") {
        const order = ["/inbox", "/reviews", "/prs", "/config"];
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
  const pathname = useLocation().pathname;
  const isInbox = pathname === "/inbox" || pathname === "/";
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: fetchInbox, enabled: false });
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta, enabled: !isInbox });
  const useQueueSource = Boolean(meta.data?.queueConfigured);
  const queue = useQueue(useQueueSource && !isInbox);
  const config = useConfig(!isInbox);
  const review = useTable("review", !useQueueSource && !isInbox);
  const team = useTable("team", !useQueueSource && !isInbox);
  const mine = useTable("mine", !useQueueSource && !isInbox);
  const hideAuthors = hideAuthorList(config.data?.settings);
  const reviewFilters = loadFilters("reviews-page");
  const mineFilters = loadFilters("mine-page");

  let reviewCount = 0;
  let mineCount = 0;
  let teamCount = 0;
  if (useQueueSource && queueActive(queue.data)) {
    const direct = queue.data.direct.map((item) => queueToRow(item, true));
    const teamRows = queue.data.team.map((item) => queueToRow(item, true));
    const mineRows = queue.data.mine.map((item) => queueToRow(item, false));
    reviewCount = filterRows(direct, reviewFilters, hideAuthors).length;
    teamCount = filterRows(teamRows, reviewFilters, hideAuthors).length;
    mineCount = filterRows(mineRows, mineFilters, hideAuthors).length;
  } else if (!useQueueSource) {
    reviewCount = filterRows(review.data?.rows ?? [], reviewFilters, hideAuthors).length;
    teamCount = filterRows(team.data?.rows ?? [], reviewFilters, hideAuthors).length;
    mineCount = filterRows(mine.data?.rows ?? [], mineFilters, hideAuthors).length;
  }

  return (
    <>
      <Hotkeys />
      <Layout reviewCount={reviewCount} teamCount={teamCount} mineCount={mineCount}
        inboxCount={inbox.data?.stacks.reduce((n, stack) => n + stack.prs.length, 0)}
        attentionCount={inbox.data?.stacks.flatMap(stack => stack.prs).filter(needsAttention).length}
        configCount={config.data?.settings.filter(setting => setting.error).length}>
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/prs" element={<MyPrsPage />} />
          <Route path="/inbox" element={<InboxPage />} />
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
