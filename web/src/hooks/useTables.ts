import { useQuery } from "@tanstack/react-query";

import { fetchTable } from "../lib/api";

export function useTable(kind: string, enabled = true) {
  return useQuery({
    queryKey: ["table", kind],
    queryFn: () => fetchTable(kind),
    enabled,
  });
}
