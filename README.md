# decky

Personal developer workflow CLI for reviewing GitHub pull requests from the terminal.

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv tool install git+https://github.com/camaragon/decky.git
```

You also need the [GitHub CLI](https://cli.github.com/) (`gh`) logged in for PR commands.

## Quick start

```bash
decky config init
# Edit ~/.config/decky/config.toml: set review.command, pr.dir, browser.command
decky pr list -i
```

## `decky pr list`

Lists pull requests in three buckets: review requests for you, team review requests, and your open PRs.

```bash
decky pr list          # table, default filters
decky pr list --all    # include drafts, failing checks, hidden authors
decky pr list -i       # TTY picker (Enter starts review, o opens URL, tab cycles lists)
decky pr list -m       # your PRs
decky pr list -t       # team requests only
```

Default filters hide drafts, PRs whose checks are not `pass`, and authors listed in `pr.hide_authors` (default includes `renovate`). Use `--all` or press `a` in the picker to show them.

### JSON interface (version 1)

```bash
decky pr list --json        # all three buckets, default filters
decky pr list --json --all  # include hidden PRs
decky pr list --json --mine # only the mine bucket (--team selects team)
```

JSON mode overrides interactive settings, including `-i`. Success prints one JSON
object to stdout; failures exit nonzero with an error on stderr. An empty result
uses empty arrays. `--mine` and `--team` remain mutually exclusive.

List envelope: `{"version":1,"buckets":{"review":[],"team":[],"mine":[]},"hidden":{"review":0,"team":0,"mine":0},"notes":[]}`.
Selection flags omit unselected bucket and hidden-count keys. `hidden` counts PRs
removed by the filters in each selected bucket; `notes` contains warning strings.

Each PR has these fields (snake_case is part of the interface):

| Fields                            | JSON type / meaning                                               |
| --------------------------------- | ----------------------------------------------------------------- |
| `repo`, `repo_owner`, `repo_name` | strings: `OWNER/NAME`, owner, name                                |
| `number`, `approvals`             | integers: PR number, latest approving review count                |
| `title`, `author`, `url`, `body`  | strings; deleted authors use `""`; body is Markdown               |
| `draft`                           | boolean                                                           |
| `checks`                          | `"pass"`, `"fail"`, `"pending"`, or `"none"`                      |
| `review_decision`                 | `"APPROVED"`, `"CHANGES_REQUESTED"`, `"REVIEW_REQUIRED"`, or null |
| `updated_at`                      | GitHub timestamp string (UTC ISO 8601)                            |
| `labels`                          | array of label-name strings                                       |

Consumers should check `version` and tolerate additional fields. Incompatible
changes increment the version. Lists retain the existing repo/number ordering and
GitHub limits: 50 PRs per source, 20 latest reviews, 20 review requests, 100 labels,
and 15 entries per watch setting. `notes` warns when a limit may hide data;
approval counts may then be partial. Results are snapshots, not a transaction.

## `decky pr review`

Opens or focuses a tmux window (default) or cmux workspace named `pr-<repo>-<number>`, runs `review.command`, and on the tmux path runs `browser.command` with the PR URL.

```bash
decky pr review owner/repo 123
decky pr r my-repo 5    # requires work_org when REPO has no slash
```

Checkout directory: `pr.dir/<repo-short>` (reused when origin matches; no `gh pr checkout`).

`terminal = "tmux"` is the default. Windows live in session `decky`, or the current tmux session when `$TMUX` is set. Set `terminal = "cmux"` to use cmux instead (`browser.command` is ignored on that path).

Override the config path with `DECKY_CONFIG`.

## `decky server`

Local web UI at `http://127.0.0.1:8777` (FastAPI + React). Review buttons use `review.command`. Optional `queue.command` prints `{today, mine, direct, team}` JSON for the PR queue sections; optional `jira.browse_url` links ticket keys.

```bash
pnpm -C web install && pnpm -C web build   # dev; git/wheel installs build the SPA automatically
decky server
decky server --no-open --dev               # API only; use pnpm -C web dev for the SPA
```

Optional `status.command` prints JSON with `waiting` and `running` lists (`title` and `url` per item) for the waiting strip.

Connect an MCP client:

```bash
mcp add --transport http decky http://127.0.0.1:8777/mcp
```

## Config

`decky config path` — print the file path  
`decky config list` — all keys with effective values  
`decky config get KEY` / `set KEY VALUE` / `unset KEY`  
`decky config init` — write the example file (refuse if it exists unless `--force`)  
`decky config edit` — open in `$EDITOR`

Default file: `~/.config/decky/config.toml` (mode `600` on write).

| Key                | Env                      | Purpose                                                                  |
| ------------------ | ------------------------ | ------------------------------------------------------------------------ |
| `work_org`         | `DECKY_WORK_ORG`         | Owner for bare repo names                                                |
| `interactive`      | `DECKY_INTERACTIVE`      | Default `-i` when stdin/stdout are a TTY                                 |
| `pr.dir`           | `DECKY_PR_DIR`           | Parent directory for checkouts                                           |
| `pr.hide_authors`  | `DECKY_PR_HIDE_AUTHORS`  | Hidden logins unless `--all`                                             |
| `pr.watch_teams`   | `DECKY_PR_WATCH_TEAMS`   | Extra team review sources (`org/team`)                                   |
| `pr.watch_repos`   | `DECKY_PR_WATCH_REPOS`   | Extra review candidates from `owner/repo`                                |
| `pr.watch_owners`  | `DECKY_PR_WATCH_OWNERS`  | Extra review candidates across users or organizations                    |
| `review.command`   | `DECKY_REVIEW_COMMAND`   | Review pane command template                                             |
| `queue.command`    | `DECKY_QUEUE_COMMAND`    | Optional argv printing `{today, mine, direct, team}` JSON for the web UI |
| `jira.browse_url`  | `DECKY_JIRA_BROWSE_URL`  | Optional `{key}` URL template for queue Jira links                       |
| `terminal`         | `DECKY_TERMINAL`         | `tmux` (default) or `cmux`                                               |
| `tmux.bin`         | `DECKY_TMUX_BIN`         | tmux binary                                                              |
| `tmux.session`     | `DECKY_TMUX_SESSION`     | Session for PR windows                                                   |
| `browser.command`  | `DECKY_BROWSER_COMMAND`  | Opens PR URL on tmux path                                                |
| `cmux.bin`         | `DECKY_CMUX_BIN`         | cmux binary                                                              |
| `cmux.group`       | `DECKY_CMUX_GROUP`       | Workspace group (cmux path)                                              |
| `server.host`      | `DECKY_SERVER_HOST`      | Bind address (default `127.0.0.1`)                                       |
| `server.port`      | `DECKY_SERVER_PORT`      | Listen port (default `8777`)                                             |
| `server.log_level` | `DECKY_SERVER_LOG_LEVEL` | App log level (`debug` … `error`)                                        |
| `status.command`   | `DECKY_STATUS_COMMAND`   | Optional argv printing waiting/running JSON                              |

Example (also written by `decky config init`):

```toml
interactive = true
terminal = "tmux"

[pr]
dir = "~/prs"
watch_owners = ["example-org", "example-user"]

[review]
command = "your-review-agent {url}"

[browser]
command = "open -a Dia {url}"
```

Placeholders for `review.command` and `browser.command`: `{slug}` `{owner}` `{repo}` `{number}` `{url}` `{cwd}`.

Watched owners and repositories contribute open, non-archived PRs by other authors
that you have not reviewed. Duplicates appear once; your own PRs stay in `mine`.
Team sources contribute to `team` unless you are directly requested. All sources
share the usual filters. List settings accept TOML arrays or comma-separated env values.

## License

MIT. Unrelated to [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader).
