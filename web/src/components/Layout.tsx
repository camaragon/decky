import { ClipboardCheck, GitPullRequest, Inbox, Settings } from "lucide-react";
import { Link, useLocation } from "react-router";
import type { ReactNode } from "react";

import { ThemeToggle } from "./ThemeToggle";
import { cn } from "../lib/utils";

const links = [
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/reviews", label: "Reviews", icon: ClipboardCheck },
  { to: "/prs", label: "My PRs", icon: GitPullRequest },
  { to: "/config", label: "Config", icon: Settings },
];

export function Layout({ reviewCount, mineCount, inboxCount, attentionCount = 0, teamCount = 0, configCount, children }: {
  reviewCount?: number; mineCount?: number; inboxCount?: number; attentionCount?: number;
  teamCount?: number; configCount?: number; children: ReactNode;
}) {
  const location = useLocation();
  const counts: Record<string, number | undefined> = {
    "/inbox": inboxCount, "/reviews": reviewCount, "/prs": mineCount, "/config": configCount ? configCount : undefined,
  };
  return (
    <div className="layout min-h-screen bg-background">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <span className="flex items-center gap-2 font-semibold"><img src="/favicon.svg" alt="" width={24} height={24} />decky</span>
          <ThemeToggle />
        </div>
        <nav aria-label="Main navigation">
          {links.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to || (to === "/inbox" && location.pathname === "/");
            return <Link key={to} to={to} aria-current={active ? "page" : undefined} className={cn("nav-link", active && "active")}>
              <Icon aria-hidden="true" size={18} />
              <span className="nav-label">{label}</span>
              <span className="nav-counts">
                {to === "/inbox" && attentionCount > 0 ? <span className="count count-danger" title="Needs attention" aria-label={`${attentionCount} need attention`}>{attentionCount}</span> : null}
                {counts[to] !== undefined ? <span className={cn("count", to === "/reviews" && "count-blue", to === "/config" && "count-amber")} aria-label={`${counts[to]} ${to === "/reviews" ? "requested from you" : to === "/config" ? "invalid settings" : "total"}`}>{counts[to]}</span> : null}
                {to === "/reviews" && teamCount > 0 ? <span className="count" title="Via team" aria-label={`${teamCount} via team`}>{teamCount}</span> : null}
              </span>
            </Link>;
          })}
        </nav>
      </aside>
      <main id="main-content" className="min-w-0">{children}</main>
    </div>
  );
}
