import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConfigPage } from "./Config";
import type { ConfigSetting } from "../lib/api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("saves effective text, shows errors, resets after unset and preserves unrelated edits", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const row: ConfigSetting = {
    key: "interactive",
    value: "true",
    source: "file",
    help: "interactive",
    kind: "bool",
  };
  const requests: string[] = [];
  let fail = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        requests.push(init.body as string);
        if (fail)
          return Response.json({ message: "interactive must be true or false" }, { status: 422 });
        row.value = JSON.parse(init.body as string).value;
      }
      if (init?.method === "DELETE") {
        row.value = "false";
        row.source = "default";
      }
      return Response.json(
        init?.method ? { message: "saved" } : { path: "/tmp/config.toml", settings: [{ ...row }] },
      );
    }),
  );
  render(
    <QueryClientProvider client={client}>
      <ConfigPage />
    </QueryClientProvider>,
  );
  const input = await screen.findByRole("textbox", { name: "interactive" });
  const user = userEvent.setup();
  client.setQueryData(["meta"], { queueConfigured: false });
  client.setQueryData(["queue"], { disabled: true });
  client.setQueryData(["status"], { disabled: true });
  client.setQueryData(["table", "mine"], { rows: [], notes: [] });
  await user.click(screen.getByText("Save"));
  await waitFor(() => expect(input).toBeEnabled());
  expect(requests).toEqual(['{"value":"true"}']);
  for (const key of [["meta"], ["queue"], ["status"], ["table", "mine"]]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  }
  await user.clear(input);
  await user.type(input, "unsaved");
  await client.refetchQueries({ queryKey: ["config"] });
  expect(input).toHaveValue("unsaved");
  fail = true;
  await user.click(screen.getByText("Save"));
  expect(await screen.findByRole("alert")).toHaveTextContent("interactive must be true or false");
  expect(input).toHaveValue("unsaved");
  await user.click(screen.getByText("Unset"));
  await waitFor(() => expect(input).toHaveValue("false"));
  expect(screen.getByText("default")).toBeInTheDocument();
});

it("recovers from an initial config failure", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ message: "cannot read config" }, { status: 422 }))
    .mockImplementation(async () => Response.json({ path: "/tmp/config.toml", settings: [] }));
  vi.stubGlobal("fetch", fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConfigPage />
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("cannot read config");
  await userEvent.click(screen.getByText("Retry config"));
  expect(await screen.findByRole("heading", { name: "Config" })).toBeInTheDocument();
});

it("shows an invalid key's error and still unsets it", async () => {
  const row: ConfigSetting = {
    key: "interactive",
    value: "perhaps",
    source: "file",
    help: "interactive",
    kind: "bool",
    error: "interactive (file) must be true or false",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        Object.assign(row, { value: "false", source: "default", error: null });
        return Response.json({ message: "removed interactive" });
      }
      return Response.json({
        path: "/tmp/config.toml",
        settings: [{ ...row }],
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConfigPage />
    </QueryClientProvider>,
  );
  const input = await screen.findByRole("textbox", { name: "interactive" });
  expect(input).toHaveValue("perhaps");
  expect(screen.getByRole("alert")).toHaveTextContent("interactive (file) must be true or false");
  await userEvent.click(screen.getByText("Unset"));
  await waitFor(() => expect(input).toHaveValue("false"));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByText("removed interactive")).toBeInTheDocument();
});
