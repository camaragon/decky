import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.history.replaceState({}, "", "/"); });

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

it.each([[false, "Ready to decide"], [true, "Not ready"]])("groups an unreviewed approved PR by whether review results are enabled (%s)", async (enabled, group) => {
  window.history.replaceState({}, "", "/inbox");
  const pr = {
    repo: "example/demo", number: 102, title: "Tidy report headers", checks: "pass",
    review_decision: "APPROVED", draft: false, url: "https://example.com/pull/102",
    head_sha: "b".repeat(40), body: "", changed_files: 0, files: [], image_urls: [],
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ owners: ["example"], all_owners: false, stacks: [{ repo: pr.repo, prs: [pr] }], notes: [], decision_enabled: false, review_results_enabled: enabled }))));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const heading = await screen.findByRole("heading", { name: "Tidy report headers" });
  expect(heading.closest("section")!.querySelector("h2")).toHaveTextContent(group);
  client.clear();
});

it("scopes keyboard answers to the focused stack member or the whole stack", async () => {
  localStorage.setItem("decky.theme", "light");
  window.history.replaceState({}, "", "/inbox");
  const member = (number: number, sha: string) => ({
    repo: "example/demo", number, title: `Stack part ${number}`, checks: "pass", review_decision: "APPROVED", draft: false,
    url: `https://example.com/pull/${number}`, head_sha: sha.repeat(40), body: "", changed_files: 0, files: [], image_urls: [],
  });
  const posts: { scope: string; numbers: number[]; note: string }[] = [];
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/inbox/decision") { posts.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify({ message: "Answer delivered" })); }
    return new Response(JSON.stringify({ owners: ["example"], all_owners: false, stacks: [{ repo: "example/demo", prs: [member(1, "c"), member(2, "d")] }], notes: [], decision_enabled: true, review_results_enabled: false }));
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const card = (await screen.findByRole("heading", { name: "Stack part 2" })).closest("article")!;
  expect(card.querySelector(".stack-header")).toHaveTextContent("No review yet");
  const summary = screen.getAllByText("Answer only this PR")[1];
  summary.focus();
  await userEvent.keyboard("n");
  expect(summary.closest("details")!.open).toBe(true);
  expect(screen.getByLabelText("Optional note for PR #2")).toBeVisible();
  await userEvent.type(screen.getByLabelText("Optional note for PR #2"), "Check the export");
  await userEvent.click(within(summary.closest("details")!).getByRole("button", { name: "Add a note" }));
  expect(screen.queryByLabelText("Optional note for PR #2")).not.toBeInTheDocument();
  expect(within(summary.closest("details")!).getByRole("button", { name: /Merge with note/ })).toBeVisible();
  summary.focus();
  await userEvent.keyboard("m");
  await vi.waitFor(() => expect(posts).toHaveLength(1));
  expect(confirm).not.toHaveBeenCalled();
  expect(posts[0].note).toBe("Check the export");
  card.focus();
  await userEvent.keyboard("h");
  expect(confirm).toHaveBeenLastCalledWith("Hold all 2 PRs?");
  await userEvent.keyboard("m");
  expect(confirm).toHaveBeenLastCalledWith("Merge all 2 PRs?");
  expect(posts).toHaveLength(1);
  confirm.mockReturnValue(true);
  await userEvent.keyboard("h");
  await vi.waitFor(() => expect(posts).toHaveLength(2));
  expect(posts.map(p => [p.scope, p.numbers])).toEqual([["pr", [2]], ["stack", [1, 2]]]);
  client.clear();
});
