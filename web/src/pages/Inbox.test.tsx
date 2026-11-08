import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); });

it("loads and refreshes the inbox without requesting proxy-forbidden APIs", async () => {
  localStorage.setItem("decky.theme", "light");
  window.history.replaceState({}, "", "/inbox");
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    requests.push(url);
    if (url !== "/api/inbox") return new Response(JSON.stringify({ message: "Forbidden" }), { status: 403 });
    return new Response(JSON.stringify({ owners: [], all_owners: false, stacks: [], notes: [], decision_enabled: false }));
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  expect(await screen.findByText(/Configure review.owners/)).toBeInTheDocument();
  expect(requests).toEqual(["/api/inbox"]);
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(requests).toEqual(["/api/inbox", "/api/inbox"]);
  client.clear();
});

it("says no PRs were found instead of the setup hint when all owners are searched", async () => {
  window.history.replaceState({}, "", "/inbox");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ owners: [], all_owners: true, stacks: [], notes: [], decision_enabled: false }))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  expect(await screen.findByText("No open PRs were found.")).toBeInTheDocument();
  expect(screen.queryByText(/Configure review.owners/)).not.toBeInTheDocument();
  client.clear();
});

it.each([false, true])("shows local risk in the row and both opinions in the expanded card (outdated: %s)", async outdated => {
  window.history.replaceState({}, "", "/inbox");
  const pr = {
    repo: "example/demo", number: 101, title: "Add report exports", checks: "pass",
    review_decision: "APPROVED", draft: false, url: "https://example.com/pull/101",
    head_sha: "a".repeat(40), body: "Description fallback", changed_files: 0, files: [], image_urls: [],
    review_result: {
      version: 1, head_sha: "a".repeat(40), risk: "medium", outdated,
      reviewer: "Primary reviewer", generated_at: "2026-11-07T12:00:00Z",
      summary: { what_changed: "Add an export button.", why: "Save reports locally.", what_to_check: "Try an empty report." },
      second_opinion: { reviewer: "Second reviewer", risk: "high", summary: "Check exported fields. <script>example</script>" },
    },
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ owners: ["example"], all_owners: false, stacks: [{ repo: pr.repo, prs: [pr] }], notes: [], decision_enabled: false }))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const heading = await screen.findByRole("heading", { name: "Add report exports" });
  const card = heading.closest("article")!;
  expect(card).toHaveTextContent("Risk: medium");
  expect(card.textContent?.includes("Outdated result")).toBe(outdated);
  expect(screen.getAllByText("Add an export button.")[0]).toBeVisible();
  await userEvent.click(screen.getByText(/Why · what to check/));
  for (const text of ["Save reports locally.", "Try an empty report.", "Second reviewer", "Risk: high", "Check exported fields. <script>example</script>"]) {
    expect(screen.getByText(text)).toBeVisible();
  }
  expect(screen.queryByText(/the PR head has changed/) !== null).toBe(outdated);
  expect(document.querySelector("section[aria-label='Review summary'] script")).toBeNull();
  expect(screen.queryByText("Description fallback")).not.toBeVisible();
  client.clear();
});
