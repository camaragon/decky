import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConfigPage } from "./Config";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

vi.mock("../hooks/useConfig", () => ({
  useConfig: () => ({
    isLoading: false,
    refetch: vi.fn(),
    data: {
      path: "/tmp/config.toml",
      settings: [
        {
          key: "pr.hide_authors",
          value: '["renovate"]',
          source: "file",
          help: "hidden",
          kind: "list_str",
        },
      ],
    },
  }),
}));

describe("ConfigPage", () => {
  it("renders settings from config", () => {
    wrap(<ConfigPage />);
    expect(screen.getByLabelText("pr.hide_authors")).toBeInTheDocument();
  });
});
