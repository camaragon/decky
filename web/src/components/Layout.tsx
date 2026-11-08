import { Link, useLocation } from "react-router";
import type { ReactNode } from "react";

import { useQuery } from "@tanstack/react-query";

import { fetchMeta } from "../lib/api";
import { QueryFeedback } from "./QueryFeedback";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

const links = [
  { to: "/", label: "Reviews" },
  { to: "/prs", label: "My PRs" },
  { to: "/inbox", label: "Inbox" },
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
  const isInbox = location.pathname === "/inbox";
  const collapsed = localStorage.getItem("decky.sidebar") === "collapsed";
  const counts: Record<string, number> = { "/": reviewCount, "/prs": mineCount };
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta, enabled: !isInbox });

  return (
    <div
      className={cn(
        "grid min-h-screen bg-background layout",
        collapsed ? "grid-cols-[3rem_1fr]" : "grid-cols-[14rem_1fr]",
      )}
    >
      <aside className="flex flex-col border-r border-border bg-sidebar px-2 py-2">
        <div className={cn("mb-2 flex items-center justify-between gap-1", collapsed && "flex-col")}>
          <span className="flex items-center gap-1.5 text-sm font-bold tracking-tight">
            <img
              src="/favicon.svg"
              alt={collapsed ? "Decky" : ""}
              width={16}
              height={16}
              className="shrink-0 [color-scheme:light] dark:[color-scheme:dark]"
            />
            {!collapsed ? "decky" : null}
          </span>
          <ThemeToggle />
          <Button
            type="button"
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
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
        {!isInbox && !collapsed ? <QueryFeedback label="settings" query={meta} /> : null}
        <nav className="flex flex-col gap-0.5">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              title={link.label}
              className={cn(
                "min-h-11 flex items-center rounded-md px-2 py-1.5 text-xs hover:bg-accent",
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
