import { Input } from "./ui/input";
import type { FilterState } from "../lib/filters";

const checksOptions = ["pass", "fail", "pending", "none", "all"];
const draftOptions = ["no", "yes", "all"];
const approvalOptions = ["any", "0", "≥1"];

export function PrFilterBar({
  filters,
  onChange,
  onReset,
}: {
  filters: FilterState;
  onChange: (next: FilterState) => void;
  onReset: () => void;
}) {
  return (
    <div className="pr-filter-bar">
      <FilterSelect
        label="Checks"
        value={filters.checks}
        options={checksOptions}
        onChange={(checks) => onChange({ ...filters, checks })}
      />
      <FilterSelect
        label="Draft"
        value={filters.draft}
        options={draftOptions}
        onChange={(draft) => onChange({ ...filters, draft })}
      />
      <label className="flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        Repo
        <Input
          name="repo"
          autoComplete="off"
          className="w-36"
          value={filters.repo}
          onChange={(e) => onChange({ ...filters, repo: e.target.value })}
        />
      </label>
      <FilterSelect
        label="Approvals"
        value={filters.approvals}
        options={approvalOptions}
        onChange={(approvals) => onChange({ ...filters, approvals })}
      />
      <label className="flex items-center gap-1.5 self-center text-xs">
        <input
          type="checkbox"
          checked={filters.hideAuthors}
          onChange={(e) => onChange({ ...filters, hideAuthors: e.target.checked })}
        />
        Hide configured authors
      </label>
      <label className="flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        Search
        <Input
          name="search"
          autoComplete="off"
          className="w-44"
          value={filters.search}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
        />
      </label>
      <button type="button" className="text-xs text-muted-foreground underline-offset-2 hover:underline" onClick={onReset}>
        Reset (a)
      </button>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
      {label}
      <select
        className="h-7 rounded-md border border-input bg-background px-2 text-xs"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    </label>
  );
}
