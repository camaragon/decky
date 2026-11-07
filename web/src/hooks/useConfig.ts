import { useQuery } from "@tanstack/react-query";

import { fetchConfig } from "../lib/api";

export function useConfig(enabled = true) {
  return useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
    enabled,
  });
}

export function hideAuthorList(settings: { key: string; value: string | null }[] | undefined): string[] {
  const row = settings?.find((s) => s.key === "pr.hide_authors");
  if (!row?.value) return [];
  try {
    const parsed = JSON.parse(row.value);
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch {
    return row.value.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}
