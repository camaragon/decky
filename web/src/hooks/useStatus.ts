import { useQuery } from "@tanstack/react-query";

import { fetchStatus } from "../lib/api";

export function useStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["status"],
    queryFn: fetchStatus,
    enabled,
  });
}
