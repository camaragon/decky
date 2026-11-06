export type PrRow = {
  number: number;
  repo: string;
  author: string;
  checks: string;
  approvals: number;
  title: string;
  draft: boolean;
  url: string;
  updated_at?: string;
  opened?: string;
  jira?: string[];
  reviewed?: boolean;
};

export type QueuePr = {
  number: number;
  repo: string;
  title: string;
  author: string;
  opened: string;
  draft: boolean;
  url: string;
  jira: string[];
  reviewed?: boolean;
};

export type QueueResponse =
  | { disabled: true }
  | {
      disabled: false;
      today: string;
      mine: QueuePr[];
      direct: QueuePr[];
      team: QueuePr[];
    };

export type TableResponse = { rows: PrRow[]; notes: string[] };

export type StatusItem = {
  title: string;
  url: string;
  subtitle?: string;
  state?: string;
};

export type StatusResponse =
  | { disabled: true }
  | { disabled: false; waiting: StatusItem[]; running: StatusItem[] };

export type ConfigSetting = {
  key: string;
  value: string | null;
  source: string;
  help: string;
  kind: string;
  error?: string | null;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.message || res.statusText);
  }
  return body as T;
}

export const fetchMeta = () =>
  api<{
    reviewConfigured: boolean;
    queueConfigured: boolean;
    statusConfigured: boolean;
    jiraBrowseUrl: string | null;
  }>("/api/meta");

export const fetchTable = (kind: string) => api<TableResponse>(`/api/tables/${kind}`);

export const fetchQueue = () => api<QueueResponse>("/api/queue");

export const fetchStatus = () => api<StatusResponse>("/api/status");

export const fetchConfig = () =>
  api<{ path: string; settings: ConfigSetting[] }>("/api/config");

export const postReview = (repo: string, number: number) =>
  api<{ message: string }>("/api/prs/review", {
    method: "POST",
    body: JSON.stringify({ repo, number }),
  });

export const postOpenUrl = (url: string) =>
  api<{ message: string }>("/api/open-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });

export const putConfig = (key: string, value: string) =>
  api<{ message: string }>(`/api/config/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });

export const deleteConfig = (key: string) =>
  api<{ message: string }>(`/api/config/${encodeURIComponent(key)}`, { method: "DELETE" });
