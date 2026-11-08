import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import * as api from "../lib/api";
import { ReviewsPage } from "./Reviews";
import { MyPrsPage } from "./MyPrs";

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("decky.theme", "light");
  vi.spyOn(api, "fetchMeta").mockResolvedValue({
    reviewConfigured: false,
    queueConfigured: false,
    jiraBrowseUrl: null,
  });
  vi.spyOn(api, "fetchConfig").mockResolvedValue({ path: "/tmp/config.toml", settings: [] });
  vi.spyOn(api, "fetchTable").mockResolvedValue({ rows: [], notes: [] });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each([ReviewsPage, MyPrsPage])(
  "distinguishes loading, failure, partial results and empty success",
  async (Page) => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    vi.mocked(api.fetchTable).mockImplementation(() => new Promise(() => {}));
    render(
      <QueryClientProvider client={client}>
        <Page />
      </QueryClientProvider>,
    );
    expect(await screen.findAllByText(/Loading .*…/)).not.toHaveLength(0);
    expect(screen.queryByText(/no (review requests|open PRs by you)/)).not.toBeInTheDocument();
    vi.mocked(api.fetchTable).mockRejectedValue(new Error("GitHub authentication required"));
    await client.cancelQueries({ queryKey: ["table"] });
    await client.refetchQueries({ queryKey: ["table"] });
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent(
      "GitHub authentication required",
    );
    expect(screen.queryByText(/no (review requests|open PRs by you)/)).not.toBeInTheDocument();
    vi.mocked(api.fetchTable).mockResolvedValue({
      rows: [],
      notes: ["Results truncated at page limit"],
    });
    await userEvent.click(screen.getAllByRole("button", { name: /Retry/ })[0]);
    expect((await screen.findAllByRole("note"))[0]).toHaveTextContent("Results truncated");
    expect(screen.getByText(/no (review requests|open PRs by you)/)).toBeInTheDocument();
    client.setQueryData(["table", Page === ReviewsPage ? "review" : "mine"], {
      rows: [
        {
          number: 1,
          repo: "sample/repo",
          author: "dev",
          checks: "pass",
          approvals: 0,
          title: "Earlier result",
          draft: false,
          url: "https://github.com/sample/repo/pull/1",
        },
      ],
      notes: ["Results truncated at page limit"],
    });
    vi.mocked(api.fetchTable).mockRejectedValue(new Error("rate limit reached"));
    await client.refetchQueries({ queryKey: ["table"] });
    await waitFor(() =>
      expect(screen.getAllByRole("alert")[0]).toHaveTextContent("showing previous data"),
    );
    expect(screen.getAllByRole("note")[0]).toHaveTextContent("Results truncated");
    expect(screen.getByText("Earlier result")).toBeInTheDocument();
  },
);

it.each([ReviewsPage, MyPrsPage])(
  "queue failures stay retryable without an empty success",
  async (Page) => {
    vi.mocked(api.fetchMeta).mockResolvedValue({
      reviewConfigured: false,
      queueConfigured: true,
      jiraBrowseUrl: null,
    });
    vi.spyOn(api, "fetchQueue")
      .mockRejectedValueOnce(new Error("queue.command cannot launch"))
      .mockResolvedValue({ disabled: false, today: "2026-01-01", mine: [], direct: [], team: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Page />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("queue.command cannot launch");
    expect(screen.queryByText(/no (review requests|open PRs by you)/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Retry queue"));
    expect(await screen.findByText(/no (review requests|open PRs by you)/)).toBeInTheDocument();
  },
);
