import type { PrRow } from "./api";

export type FilterState = {
  checks: string;
  draft: string;
  repo: string;
  approvals: string;
  hideAuthors: boolean;
  search: string;
};

export const defaultFilters = (): FilterState => ({
  checks: "pass",
  draft: "no",
  repo: "",
  approvals: "any",
  hideAuthors: true,
  search: "",
});

const STORAGE = "decky.filters";

export function loadFilters(kind: string): FilterState {
  try {
    const raw = localStorage.getItem(`${STORAGE}.${kind}`);
    if (!raw) return defaultFilters();
    return { ...defaultFilters(), ...JSON.parse(raw) };
  } catch {
    return defaultFilters();
  }
}

export function saveFilters(kind: string, filters: FilterState) {
  localStorage.setItem(`${STORAGE}.${kind}`, JSON.stringify(filters));
}

export function authorHidden(author: string, hidden: string[]): boolean {
  const login = author.toLowerCase().replace(/\[bot\]$/i, "");
  return hidden.some((h) => h.toLowerCase().replace(/\[bot\]$/i, "") === login);
}

export function filterRows(rows: PrRow[], filters: FilterState, hideAuthors: string[]): PrRow[] {
  return rows.filter((row) => {
    if (filters.checks !== "all" && row.checks !== filters.checks) return false;
    if (filters.draft === "no" && row.draft) return false;
    if (filters.draft === "yes" && !row.draft) return false;
    if (filters.repo && !row.repo.toLowerCase().includes(filters.repo.toLowerCase())) return false;
    if (filters.approvals === "0" && row.approvals !== 0) return false;
    if (filters.approvals === "≥1" && row.approvals < 1) return false;
    if (filters.hideAuthors && authorHidden(row.author, hideAuthors)) return false;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      if (!row.repo.toLowerCase().includes(q) && !row.title.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

export function visibleCount(rows: PrRow[], filters: FilterState, hideAuthors: string[]): number {
  return filterRows(rows, filters, hideAuthors).length;
}
