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

it("starts stacks and PR details collapsed and expands them on click", async () => {
  window.history.replaceState({}, "", "/inbox");
  const pr = { repo: "example/demo", number: 101, title: "Improve navigation", checks: "fail", review_decision: "CHANGES_REQUESTED", draft: true, url: "https://example.com/pull/101", head_sha: "demo", body: "Example description", changed_files: 0, files: [], image_urls: [] };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ owners: ["example"], all_owners: false, stacks: [{ repo: pr.repo, prs: [pr, { ...pr, number: 102, title: "Update copy", checks: "pass", review_decision: "APPROVED", draft: false }] }], notes: [], decision_enabled: true }))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const stackSummary = await screen.findByText(/2 PR stack/);
  const stack = stackSummary.closest("details")!;
  const heading = screen.getByRole("heading", { name: /#101 Improve navigation/, hidden: true });
  const details = heading.closest("details")!;
  const secondDetails = screen.getByRole("heading", { name: /#102 Update copy/, hidden: true }).closest("details")!;
  expect(stack).not.toHaveAttribute("open");
  expect(details).not.toHaveAttribute("open");
  expect(secondDetails).not.toHaveAttribute("open");
  await userEvent.click(stackSummary);
  expect(stack).toHaveAttribute("open");
  expect(details).not.toHaveAttribute("open");
  const row = heading.closest("summary")!;
  expect(row).toHaveTextContent("Checks: fail");
  expect(row).toHaveTextContent("CHANGES REQUESTED");
  expect(row).toHaveTextContent("Draft");
  await userEvent.click(heading);
  expect(details).toHaveAttribute("open");
  expect(screen.getByRole("textbox", { name: "Optional note for PR #101" })).toBeVisible();
  expect(secondDetails).not.toHaveAttribute("open");
  await userEvent.click(heading);
  expect(details).not.toHaveAttribute("open");
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
  await userEvent.click(await screen.findByText(/Single PR/));
  const heading = screen.getByRole("heading", { name: /#101 Add report exports/ });
  const row = heading.closest("summary")!;
  expect(row).toHaveTextContent("Risk: medium");
  expect(row.textContent?.includes("Outdated result")).toBe(outdated);
  expect(screen.getByText("Add an export button.")).not.toBeVisible();
  await userEvent.click(heading);
  for (const text of ["Add an export button.", "Save reports locally.", "Try an empty report.", "Second reviewer", "Risk: high", "Check exported fields. <script>example</script>"]) {
    expect(screen.getByText(text)).toBeVisible();
  }
  expect(screen.queryByText(/the PR head has changed/) !== null).toBe(outdated);
  expect(document.querySelector("section[aria-label='Review summary'] script")).toBeNull();
  expect(screen.queryByText("Description fallback")).not.toBeVisible();
  client.clear();
});
