import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../components/ui/button";
import { QueryFeedback } from "../components/QueryFeedback";

import { type ConfigSetting, deleteConfig, putConfig } from "../lib/api";
import { useConfig } from "../hooks/useConfig";

export function ConfigPage() {
  const query = useConfig();
  const { data } = query;
  const client = useQueryClient();

  if (!data) return <QueryFeedback label="config" query={query} />;

  return (
    <div className="config-page">
      <header className="page-header"><div><h1>Config</h1><p>Effective settings, grouped by purpose.</p></div></header>
      <QueryFeedback label="config" query={query} />
      <p className="config-path">{data.path}</p>
      {[...new Set(data.settings.map(s => s.key.includes(".") ? s.key.split(".")[0] : "general"))].map(group => <section key={group} className="config-group">
        <h2>{group}</h2>
        <table className="config-table"><tbody>
          {data.settings.filter(s => (s.key.includes(".") ? s.key.split(".")[0] : "general") === group).map(s => <ConfigRow key={s.key} setting={s} onSaved={() => client.invalidateQueries()} />)}
        </tbody></table>
      </section>)}
    </div>
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
      <th scope="row"><span>{setting.key}</span><p>{setting.help}</p></th>
      <td>
        <input
          name={setting.key}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={Boolean(setting.error || error)}
          disabled={busy}
          value={value ?? setting.value ?? ""}
          onChange={(e) => setValue(e.target.value)}
          aria-label={setting.key}
        />
      </td>
      <td>
        <span className="fact">{setting.source}</span>
        {setting.error ? <span role="alert">{setting.error}</span> : null}
      </td>
      <td>
        <Button size="sm" variant="outline" type="button" disabled={busy} onClick={() => mutate(false)}>
          Save
        </Button>
        <Button size="sm" variant="outline" type="button" disabled={busy} onClick={() => mutate(true)}>
          Unset
        </Button>
        {error ? <span role="alert">{error}</span> : null}
        {msg ? <span role="status">{msg}</span> : null}
      </td>
    </tr>
  );
}
