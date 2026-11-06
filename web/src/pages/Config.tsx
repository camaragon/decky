import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QueryFeedback } from "../components/QueryFeedback";

import { type ConfigSetting, deleteConfig, putConfig } from "../lib/api";
import { useConfig } from "../hooks/useConfig";

export function ConfigPage() {
  const query = useConfig();
  const { data } = query;
  const client = useQueryClient();

  if (!data) return <QueryFeedback label="config" query={query} />;

  return (
    <section>
      <h1>Config</h1>
      <QueryFeedback label="config" query={query} />
      <p>{data.path}</p>
      <table>
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Source</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.settings.map((s) => (
            <ConfigRow key={s.key} setting={s} onSaved={() => client.invalidateQueries()} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ConfigRow({ setting, onSaved }: { setting: ConfigSetting; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function mutate(unset: boolean) {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const res = unset
        ? await deleteConfig(setting.key)
        : await putConfig(setting.key, value ?? setting.value ?? "");
      await onSaved();
      setValue(null);
      setMsg(res.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr>
      <td title={setting.help}>{setting.key}</td>
      <td>
        <input
          disabled={busy}
          value={value ?? setting.value ?? ""}
          onChange={(e) => setValue(e.target.value)}
          aria-label={setting.key}
        />
      </td>
      <td>
        {setting.source}
        {setting.error ? <span role="alert">{setting.error}</span> : null}
      </td>
      <td>
        <button type="button" disabled={busy} onClick={() => mutate(false)}>
          Save
        </button>
        <button type="button" disabled={busy} onClick={() => mutate(true)}>
          Unset
        </button>
        {error ? <span role="alert">{error}</span> : null}
        {msg ? <span>{msg}</span> : null}
      </td>
    </tr>
  );
}
