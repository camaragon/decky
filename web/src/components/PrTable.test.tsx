import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PrSection } from "./PrSection";
import * as api from "../lib/api";
import { defaultFilters } from "../lib/filters";

const rows = [
  {
    number: 9,
    repo: "acme/api",
    author: "dev",
    checks: "pass",
    approvals: 0,
    title: "Feature",
    draft: false,
    url: "https://github.com/acme/api/pull/9",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    number: 2,
    repo: "acme/api",
    author: "dev",
    checks: "pass",
    approvals: 0,
    title: "Draft thing",
    draft: true,
    url: "https://github.com/acme/api/pull/2",
    updated_at: "2026-01-02T00:00:00Z",
  },
];

describe("PrSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("posts review to /api/prs/review", async () => {
    const post = vi.spyOn(api, "postReview").mockResolvedValue({ message: "ok" });
    render(
      <PrSection
        title="Review"
        rows={rows}
        hideAuthors={[]}
        filters={defaultFilters()}
        empty="none"
        reviewAction
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Review" }));
    expect(post).toHaveBeenCalledWith("acme/api", 9);
  });

  it("hides drafts with default filters", () => {
    render(
      <PrSection
        title="Review"
        rows={rows}
        hideAuthors={[]}
        filters={defaultFilters()}
        empty="none"
        reviewAction
      />,
    );
    expect(screen.getByText("Feature")).toBeInTheDocument();
    expect(screen.queryByText("Draft thing")).not.toBeInTheDocument();
  });

  it("hides renovate when hideAuthors on", () => {
    render(
      <PrSection
        title="Review"
        rows={[
          ...rows,
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
        ]}
        hideAuthors={["renovate"]}
        filters={defaultFilters()}
        empty="none"
        reviewAction
      />,
    );
    expect(screen.queryByText("Bump")).not.toBeInTheDocument();
  });
});
