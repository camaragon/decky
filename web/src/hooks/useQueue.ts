import { useQuery } from "@tanstack/react-query";

import { fetchQueue, type QueueResponse } from "../lib/api";

export function useQueue(enabled: boolean) {
  return useQuery({
    queryKey: ["queue"],
    queryFn: fetchQueue,
    enabled,
  });
}

export function queueActive(data: QueueResponse | undefined): data is Extract<QueueResponse, { disabled: false }> {
  return Boolean(data && !data.disabled);
}
