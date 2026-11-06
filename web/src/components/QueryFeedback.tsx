export function QueryFeedback({
  label,
  query,
}: {
  label: string;
  query: { isLoading: boolean; error: Error | null; data?: unknown; refetch: () => unknown };
}) {
  return (
    <>
      {query.isLoading && !query.data ? <p>Loading {label}…</p> : null}
      {query.error ? (
        <p role="alert">
          {label}: {query.error.message}
          {query.data ? " (showing previous data)" : ""}{" "}
          <button type="button" onClick={() => query.refetch()}>
            Retry {label}
          </button>
        </p>
      ) : null}
      {((query.data as { notes?: string[] } | undefined)?.notes ?? []).map((note, i) => (
        <p role="note" key={i}>
          {note}
        </p>
      ))}
    </>
  );
}
