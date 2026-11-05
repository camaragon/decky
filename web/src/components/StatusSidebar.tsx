import { useState } from "react";

import type { StatusItem } from "../lib/api";
import { postOpenUrl } from "../lib/api";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

export function StatusSidebar({
  waiting,
  running,
  error,
  onRefresh,
}: {
  waiting: StatusItem[];
  running: StatusItem[];
  error: string | null;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function open(url: string) {
    setBusy(url);
    try {
      await postOpenUrl(url);
    } finally {
      setBusy(null);
    }
  }

  if (!waiting.length && !running.length && !error) {
    return null;
  }

  return (
    <div className="mb-3 space-y-2 border-b border-border pb-3">
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Status
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={onRefresh}>
          Refresh
        </Button>
      </div>
      {error ? <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p> : null}
      {waiting.length ? (
        <ul className="space-y-1">
          {waiting.map((item) => (
            <li key={item.url}>
              <StatusRow item={item} highlight busy={busy === item.url} onOpen={() => open(item.url)} />
            </li>
          ))}
        </ul>
      ) : null}
      {running.length ? (
        <ul className="mt-2 space-y-1 border-t border-border pt-2">
          {running.map((item) => (
            <li key={item.url}>
              <StatusRow item={item} busy={busy === item.url} onOpen={() => open(item.url)} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function StatusRow({
  item,
  highlight,
  busy,
  onOpen,
}: {
  item: StatusItem;
  highlight?: boolean;
  busy: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onOpen}
      className={cn(
        "w-full rounded-md px-2 py-1.5 text-left text-[11px] leading-tight transition-colors hover:bg-accent",
        highlight && "bg-sidebar-accent font-medium",
      )}
    >
      <div className="truncate">{item.title}</div>
      {item.subtitle ? (
        <div className="truncate text-muted-foreground">{item.subtitle}</div>
      ) : null}
      {item.state ? <div className="text-[10px] text-muted-foreground">{item.state}</div> : null}
    </button>
  );
}
