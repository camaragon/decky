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
    return new Response(JSON.stringify({ owners: [], stacks: [], notes: [], decision_enabled: false }));
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  expect(await screen.findByText(/Configure review.owners/)).toBeInTheDocument();
  expect(requests).toEqual(["/api/inbox"]);
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(requests).toEqual(["/api/inbox", "/api/inbox"]);
  client.clear();
});
