import { Link, useLocation } from "react-router";
import type { ReactNode } from "react";

import { useQuery } from "@tanstack/react-query";

import { fetchMeta } from "../lib/api";
import { useStatus } from "../hooks/useStatus";
import { QueryFeedback } from "./QueryFeedback";
import { StatusSidebar } from "./StatusSidebar";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

const links = [
  { to: "/", label: "Reviews" },
  { to: "/prs", label: "My PRs" },
  { to: "/config", label: "Config" },
];

export function Layout({
  reviewCount,
  mineCount,
  children,
}: {
  reviewCount: number;
  mineCount: number;
  children: ReactNode;
}) {
  const location = useLocation();
  const collapsed = localStorage.getItem("decky.sidebar") === "collapsed";
  const counts: Record<string, number> = { "/": reviewCount, "/prs": mineCount };
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const status = useStatus(Boolean(meta.data?.statusConfigured));
  const statusPayload = status.data && !status.data.disabled ? status.data : null;

  return (
    <div
      className={cn(
        "grid min-h-screen bg-background",
        collapsed ? "grid-cols-[3rem_1fr]" : "grid-cols-[14rem_1fr]",
      )}
    >
      <aside className="flex flex-col border-r border-border bg-sidebar px-2 py-2">
        <div className="mb-2 flex items-center justify-between gap-1">
          {!collapsed ? <span className="text-sm font-bold tracking-tight">decky</span> : null}
          <ThemeToggle />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="shrink-0"
            onClick={() => {
              const next = collapsed ? "expanded" : "collapsed";
              localStorage.setItem("decky.sidebar", next);
              window.location.reload();
            }}
          >
            {collapsed ? "»" : "«"}
          </Button>
        </div>
        {!collapsed ? <QueryFeedback label="settings" query={meta} /> : null}
        {!collapsed && meta.data?.statusConfigured ? (
          <QueryFeedback label="status" query={status} />
        ) : null}
        {!collapsed && statusPayload ? (
          <StatusSidebar
            waiting={statusPayload.waiting}
            running={statusPayload.running}
            error={null}
            onRefresh={() => status.refetch()}
          />
        ) : null}
        <nav className="flex flex-col gap-0.5">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              title={link.label}
              className={cn(
                "rounded-md px-2 py-1.5 text-xs hover:bg-accent",
                location.pathname === link.to && "bg-accent font-semibold",
                collapsed && "text-center px-1",
              )}
            >
              {collapsed
                ? link.label[0]
                : `${link.label}${counts[link.to] != null ? ` (${counts[link.to]})` : ""}`}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 px-4 py-3">{children}</main>
    </div>
  );
}
