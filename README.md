# decky

Personal developer workflow CLI for reviewing GitHub pull requests from the terminal.

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv tool install git+https://github.com/camaragon/decky.git
```

You also need Git and the [GitHub CLI](https://cli.github.com/) (`gh`) logged in for PR commands. Review checkouts use `gh repo clone` with the configured GitHub protocol (`gh config get git_protocol --host github.com`), supporting HTTPS and SSH. Clones include submodules; their remotes need their own Git access and credentials. Clone progress streams to decky's terminal or server output; a failed clone stops the review with an error naming the exit code, the checkout path, and the GitHub authentication and Git access to check.

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
decky pr list --json        # all four buckets, default filters
decky pr list --json --all  # include hidden PRs
decky pr list --json --mine # only the mine bucket (--team selects team)
```

JSON mode overrides interactive settings, including `-i`. Success prints one JSON
object to stdout; failures exit nonzero with an error on stderr. An empty result
uses empty arrays. `--mine` and `--team` remain mutually exclusive.

List envelope: `{"version":1,"buckets":{"review":[],"team":[],"mine":[],"watched":[]},"hidden":{"review":0,"team":0,"mine":0,"watched":0},"notes":[]}`.
`watched` holds PRs found only through `pr.watch_owners`. Selection flags omit
unselected bucket and hidden-count keys. `hidden` counts PRs
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
and 15 entries per watch setting. `notes` warns when a limit may hide data:
`list truncated at GitHub page size` for PR lists and review requests,
`labels truncated at 100`, and `approvals may be partial (20 latest reviews)`. Results are snapshots, not a transaction.

## `decky pr show`

```bash
decky pr show owner/repo 123 --json
```

Fetches a single PR, including closed PRs, without applying list filters. Requires
an explicit `OWNER/REPO` and a positive PR number. It emits
`{"version":1,"pr":{...},"notes":[]}` with all the PR fields above plus:

- `changed_files`: integer total reported by GitHub.
- `files`: array of `{path: string, additions: integer, deletions: integer}`.
- `check_runs`: array of `{name: string, status: string, conclusion: string|null, url: string|null}`.
- `commit_statuses`: array of `{name: string, state: string, url: string|null}`.
- `image_urls`: deduplicated HTTP(S) URLs from Markdown inline/reference images,
  HTML `img` sources, bare image URLs, and GitHub attachment URLs in the body.
  Relative paths are omitted; URLs are extracted without downloading images.

Latest check runs and commit statuses describe the fetched head commit and retain
GitHub's state strings. Files, check runs, and commit statuses are paginated. The
[check-run endpoint](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
covers the 1000 most recent check suites. GitHub limits
changed-file responses to 3000 files; `notes` warns if fewer files than
`changed_files` are returned. The metadata limits above also apply.

## `decky pr review`

Opens or focuses a tmux window (default) or cmux workspace named `pr-<owner>+<repo>-<number>`, runs `review.command`, and on the tmux path runs `browser.command` with the PR URL. Owner and repository names are normalized to lowercase; `+` cannot appear in GitHub names, so these never collide with legacy `pr-<repo>-<number>` surfaces.

```bash
decky pr review owner/repo 123
decky pr r my-repo 5    # requires work_org when REPO has no slash
```

Checkout directory: `pr.dir/<owner>+<repo>` (reused only when origin matches the GitHub host and exact owner/repository, or the repository GitHub redirects that owner/repository to after a rename or transfer; no `gh pr checkout`). The origin is checked before focusing an existing review surface. Legacy `<repo-short>` directories and `pr-<repo>-<number>` surfaces are left untouched; new reviews use the owner-qualified identity.

`terminal = "tmux"` is the default. Windows live in session `decky`, or the current tmux session when `$TMUX` is set. Set `terminal = "cmux"` to use cmux instead (`browser.command` is ignored on that path).

Override the config path with `DECKY_CONFIG`.

## `decky server`

Local web UI at `http://127.0.0.1:8777` (FastAPI + React). Review buttons use `review.command`. Optional `queue.command` prints `{today, mine, direct, team}` JSON for the PR queue sections; optional `jira.browse_url` links ticket keys.

The server has no authentication. Keep the default loopback bind unless you trust everyone who can reach the listener. Non-loopback binds, including `0.0.0.0` and `::`, emit a warning. API Host filtering allows loopback names and the configured listen host; it is not authentication.

```bash
pnpm -C web install && pnpm -C web build   # dev; git/wheel installs build the SPA automatically
decky server
decky server --no-open --dev               # API only; use pnpm -C web dev for the SPA
```

The review inbox API (`GET /api/inbox`) lists your authored open PRs only in
configured `review.owners` (GitHub search: `author:@me user:OWNER` per owner). An
empty owner list makes no inbox GitHub requests. Stacks follow same-repository
base/head branch dependencies in merge order, grouped by repository; fork PRs
never join a stack through their head branch name. Summaries come from PR
descriptions; screenshots load through `GET /api/inbox/image`, an authenticated
GitHub-only attachment endpoint. Private PR content stays in the local server.

```toml
[review]
owners = ["example-org", "example-user"]
decision_command = ["/path/to/decision-hook", "--stdin"]
```

`review.decision_command` (or `DECKY_REVIEW_DECISION_COMMAND`, a JSON string array)
is an argv list executed without a shell. `POST /api/inbox/decision` sends one JSON
object on stdin:
`{"version":1,"decision":"hold","scope":"stack","repo":"example-org/example-repo","prs":[{"number":1,"url":"https://github.com/example-org/example-repo/pull/1","head_sha":"abc123"}],"note":"Please explain the migration"}`.
PRs are in merge order. The command has 30 seconds to exit successfully; failures
return an error message. A timeout may have delivered the answer, so check the
recipient before retrying. Without a command the endpoint returns 409. Decky does
not merge or approve PRs.

For phone access, run behind an authenticated reverse proxy; never expose the
unauthenticated server directly. Keep the default loopback bind and serve the SPA
at `/`. Configure exact proxy hostnames (without scheme, port, or wildcards):

```toml
[server]
allowed_hosts = ["review.example.com"]
```

`DECKY_SERVER_ALLOWED_HOSTS` also accepts a JSON array or comma-separated names.
Restart the server after changing allowed hosts; an invalid entry stops the server
from starting. Requests through an allowed host may only load the SPA and static
assets, `GET /api/inbox`, `GET /api/inbox/image`, and `POST /api/inbox/decision`.
Every other API route (config reads and writes, review launch, opening URLs,
queue, status) and `/mcp` return 403 for those requests; loopback access is
unchanged. Host filtering is not authentication: everyone able to reach the
proxy can read inbox PR content and send merge/hold answers.

Optional `status.command` prints JSON with `waiting` and `running` lists (`title` and `url` per item) for the waiting strip.

Connect an MCP client:

```bash
mcp add --transport http decky http://127.0.0.1:8777/mcp
```

HTTP and MCP configuration writes share a lock within one server instance. Separate server processes, CLI commands and external editors do not share that lock.

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
| `pr.watch_owners`  | `DECKY_PR_WATCH_OWNERS`  | Users or organizations for the JSON `watched` bucket                     |
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

[review]
command = "your-review-agent {url}"

[browser]
command = "open -a Dia {url}"
```

Placeholders for `review.command` and `browser.command`: `{slug}` `{owner}` `{repo}` `{number}` `{url}` `{cwd}`.

Watched owners and repositories contribute open, non-archived PRs by other authors
that you have not reviewed. Duplicates appear once; your own PRs stay in `mine`.
Team sources contribute to `team` unless you are directly requested. Watched
repositories contribute to `review`; watched owners contribute only PRs absent from
`review` and `team`, in the JSON `watched` bucket. All sources
share the usual filters. List settings accept TOML arrays or comma-separated env values.

## License

MIT. Unrelated to [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader).
