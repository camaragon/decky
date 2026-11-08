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
  additions?: number | null;
  deletions?: number | null;
  review_decision?: string | null;
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

export type ReviewRisk = "low" | "medium" | "high";
export type ReviewResult = {
  version: 1;
  head_sha: string;
  risk: ReviewRisk;
  summary: { what_changed: string; why: string; what_to_check: string };
  reviewer: string;
  generated_at: string;
  second_opinion: { reviewer: string; risk: ReviewRisk; summary: string } | null;
  outdated: boolean;
};

export type InboxPr = PrRow & {
  head_sha: string;
  body: string;
  review_decision: string | null;
  check_runs?: { name: string; status: string; conclusion: string | null; url: string | null }[];
  commit_statuses?: { name: string; state: string; url: string | null }[];
  changed_files: number;
  files: { path: string; additions: number; deletions: number }[];
  image_urls: string[];
  review_result?: ReviewResult;
};
export type InboxStack = { repo: string; prs: InboxPr[] };
export type InboxResponse = { owners: string[]; all_owners: boolean; stacks: InboxStack[]; notes: string[]; decision_enabled: boolean };
export const fetchInbox = () => api<InboxResponse>("/api/inbox");
export const sendAnswer = (stack: InboxStack, scope: "pr" | "stack", decision: "merge" | "hold", note: string) =>
  api<{ message: string }>("/api/inbox/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
    body: JSON.stringify({ repo: stack.repo, numbers: stack.prs.map(p => p.number), head_shas: stack.prs.map(p => p.head_sha), scope, decision, note }),
  });
