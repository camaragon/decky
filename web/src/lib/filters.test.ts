import { describe, expect, it } from "vitest";

import type { PrRow } from "./api";
import { defaultFilters, filterRows } from "./filters";

const rows: PrRow[] = [
  {
    number: 1,
    repo: "acme/api",
    author: "dev",
    checks: "pass",
    approvals: 0,
    title: "Ok",
    draft: false,
    url: "https://github.com/acme/api/pull/1",
  },
  {
    number: 2,
    repo: "acme/api",
    author: "dev",
    checks: "pass",
    approvals: 0,
    title: "Draft",
    draft: true,
    url: "https://github.com/acme/api/pull/2",
  },
  {
    number: 3,
    repo: "acme/web",
    author: "renovate",
    checks: "pass",
    approvals: 0,
    title: "Bump",
    draft: false,
    url: "https://github.com/acme/web/pull/3",
  },
];

describe("filterRows", () => {
  it("hides drafts by default", () => {
    const f = defaultFilters();
    expect(filterRows(rows, f, ["renovate"]).map((r) => r.number)).toEqual([1]);
  });

  it("shows renovate when hideAuthors off", () => {
    const f = { ...defaultFilters(), hideAuthors: false };
    expect(filterRows(rows, f, ["renovate"]).map((r) => r.number)).toEqual([1, 3]);
  });
});
