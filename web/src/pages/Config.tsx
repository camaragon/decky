import { useState } from "react";

import { deleteConfig, putConfig } from "../lib/api";
import { useConfig } from "../hooks/useConfig";

export function ConfigPage() {
  const { data, refetch, isLoading } = useConfig();

  if (isLoading || !data) return <p>Loading config…</p>;

  return (
    <section>
      <h1>Config</h1>
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
            <ConfigRow key={s.key} setting={s} onSaved={() => refetch()} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ConfigRow({
  setting,
  onSaved,
}: {
  setting: { key: string; value: string | null; source: string; help: string };
  onSaved: () => void;
}) {
  const [value, setValue] = useState(setting.value ?? "");
  const [msg, setMsg] = useState<string | null>(null);

  async function save() {
    const res = await putConfig(setting.key, value);
    setMsg(res.message);
    onSaved();
  }

  async function unset() {
    const res = await deleteConfig(setting.key);
    setMsg(res.message);
    onSaved();
  }

  return (
    <tr>
      <td title={setting.help}>{setting.key}</td>
      <td>
        <input value={value} onChange={(e) => setValue(e.target.value)} aria-label={setting.key} />
      </td>
      <td>{setting.source}</td>
      <td>
        <button type="button" onClick={save}>
          Save
        </button>
        <button type="button" onClick={unset}>
          Unset
        </button>
        {msg ? <span>{msg}</span> : null}
      </td>
    </tr>
  );
}
