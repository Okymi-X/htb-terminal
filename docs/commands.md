# Command reference

Complete reference for every `htb` command, including arguments, options,
defaults, and the Labs v4/v5 endpoints each command calls.

Run `htb <command> --help` or `htb <command> <subcommand> --help` for the
built-in help at any level.

## Global options

Global options can go before the top-level command or after the runnable leaf
command. `--version` is top-level-only and must come first:

```bash
htb --json machine active
htb --color never --wide machine list
htb machine active --json
```

| Option | Default | Description |
| --- | --- | --- |
| `--version` | — | Print `htb <version>` and exit. |
| `--token-file PATH` | auto | File to read the App Token from. When unset, `htb` looks at `./api.token` then the user config file written by `htb init`. `HTB_API_TOKEN` takes precedence over all of these. |
| `--base-url URL` | `https://labs.hackthebox.com/api/v4` | Override the API base URL. Also settable via `HTB_API_BASE_URL`. |
| `--timeout SECONDS` | `30` | HTTP request timeout. |
| `--json` | off | Print raw JSON responses instead of human-readable output. |
| `--color {auto,always,never}` | `auto` | Colorize human output. `auto` colors only when stdout is an interactive terminal. |
| `--wide` | off | Do not truncate table columns to the terminal width. |

### Environment variables

| Variable | Description |
| --- | --- |
| `HTB_API_TOKEN` | App Token. Overrides `--token-file`. `Authorization:` and `Bearer ` prefixes are stripped automatically. |
| `HTB_API_BASE_URL` | API base URL. Overridden by `--base-url`. |

### Rate limiting

When the API answers HTTP 429, requests are retried automatically with
exponential backoff (1s, 2s, 4s, 8s — up to 4 retries), honoring the
`Retry-After` header when present. Each retry prints a warning to stderr.
This mainly matters for `machine search --all --profiles`, which can scan
many pages.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | API, configuration, or input error. The message is printed to stderr as `error: ...`. |
| `2` | No command given (help is printed). |
| `130` | Interrupted with Ctrl-C. Cleanup still runs for managed OpenVPN processes. |

### Machine targets

Wherever a command takes a machine target, you can pass either a numeric id
(`444`) or a machine name (`BoardLight`). Names are resolved through
`/machine/profile/<name>`.

### Running with sudo / privilege elevation

`speedrun` launches OpenVPN and changes the tunnel MTU, so the whole command
must run as root. `vpn connect` does not require the whole CLI to run as root:
its default `sudo openvpn` command elevates only OpenVPN.

For a pipx install, resolve the executable before `sudo` so sudo's restricted
`PATH` does not hide it:

```bash
sudo "$(command -v htb)" speedrun Seasonal us-free-1
```

For a source checkout, use `sudo ./htb speedrun ...`. Do not create a
persistent `/usr/bin` symlink to a user-writable pipx executable.

Under sudo, token lookup checks `./api.token`, root's normal config path, then
the invoking user's `~/.config/htb-terminal/token` using `SUDO_USER`. The
recommended setup is therefore to run `htb init` as your normal user first. If
your token lives in a custom XDG directory, pass its expanded path explicitly:

```bash
sudo "$(command -v htb)" --token-file "$XDG_CONFIG_HOME/htb-terminal/token" \
  speedrun Seasonal us-free-1
```

An environment-only token is normally removed by sudo. Prefer a token file; if
needed and allowed by local sudo policy, preserve only the required variable
with `sudo --preserve-env=HTB_API_TOKEN ...`. Preserve `HTB_API_BASE_URL` too
only when using a custom API base.

---

## init

Save your HTB App Token so future commands find it automatically. This is the
easiest way to authenticate, especially for a global `pipx install`.

```bash
htb init
htb init --token "$MY_TOKEN"
echo "$MY_TOKEN" | htb init
```

| Option | Description |
| --- | --- |
| `--token VALUE` | Token value. If omitted, you are prompted (input hidden), or it is read from stdin when piped. |
| `--check` | After saving, verify the token against `GET /user/info` and print your username. |

The token is written to the user config file
(`~/.config/htb-terminal/token`, or `$XDG_CONFIG_HOME/htb-terminal/token`) with
owner-only permissions. Pass the global `--token-file PATH` before `init` to
save it somewhere else, for example `htb --token-file ./api.token init`.

`init` without `--check` makes no network calls and does not require an existing
token. `--check` verifies the newly saved token. `Bearer` and `Authorization:`
prefixes are stripped automatically before saving.

---

## machine

### machine profile

Show a machine profile by id or name.

```bash
htb machine profile BoardLight
htb machine profile 444
```

| Argument | Description |
| --- | --- |
| `target` | Machine id or name. |

Endpoint: `GET /machine/profile/{target}`

### machine info

Alias for `machine profile`.

```bash
htb machine info BoardLight
```

Endpoint: `GET /machine/profile/{target}`

### machine active

Show the active machine. The session response is enriched with the matching
machine profile and printed as a compact summary that includes profile-only
text such as `info_status` and `description` when HTB returns it.

```bash
htb machine active
htb machine active --details
htb --json machine active
```

| Option | Description |
| --- | --- |
| `--details` | Also include the synopsis and Academy module names. |
| `--oneline` | Print a single compact status line, e.g. `ACTIVE  BoardLight  10.10.11.11  Linux/Easy  expires in 47m  [spawned]`. |

The summary includes `expires_in`, a relative expiry such as `in 47m` derived
from the machine's expiry timestamp.

With the global `--json` flag, the full enriched response is printed instead
of the summary.

Endpoints: `GET /machine/active`, `GET /machine/profile/{id}`

### machine list

List machines as a table with columns `id`, `name`, `os`, `difficulty`,
`points`, `active`, `spawned`, `free`. Without a filter, playable (current)
machines are listed.

```bash
htb machine list
htb machine list --page 2
htb machine list --retired --page 1
htb machine list --todo
htb machine list --unreleased
htb machine list --sp-tier 1
```

| Option | Description |
| --- | --- |
| `--page N` | Page number for playable and retired lists. |
| `--retired` | List retired machines. |
| `--todo` | List machines on your to-do list. |
| `--unreleased` | List unreleased machines. |
| `--sp-tier {1,2,3}` | List Starting Point machines for the given tier. |

The filters `--retired`, `--todo`, `--unreleased`, and `--sp-tier` are
mutually exclusive; choose at most one.

Endpoints: `GET /machine/paginated`, `GET /machine/list/retired/paginated`,
`GET /machines?todo=1` (v5), `GET /machines?state=unreleased` (v5),
`GET /machines?spTier=N` (v5)

### machine search

Search machines by id, name, OS, difficulty, tag, maker, or profile text.
The search uses the documented list endpoints and filters locally; it does
not depend on an undocumented search endpoint. Results are sorted by
relevance and include a `retired` column.

```bash
htb machine search linux
htb machine search kerberos --all --limit 10
htb machine search "breach creds" --all --profiles
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `query` | — | Search text. Matches id, name, OS, difficulty, tags, maker names, and common list fields. |
| `--retired` | off | Search retired machines only. |
| `--all` | off | Search playable and retired machines. Mutually exclusive with `--retired`. |
| `--profiles` | off | Also fetch each scanned machine profile and match profile-only fields such as descriptions. Slower: one extra request per scanned machine. |
| `--limit N` | `20` | Stop after printing up to `N` matches. |
| `--max-pages N` | `10` | Cap the number of API pages scanned per list. |

### machine start

Start (spawn) a machine by id or name.

```bash
htb machine start BoardLight
htb machine start 444 --mode play
htb machine start 478 --mode spawn
htb machine start Seasonal --wait
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `target` | — | Machine id or name. |
| `--mode {auto,play,spawn}` | `auto` | Which start endpoint to use. |
| `--wait` | off | Retry while spawn capacity is full, then wait for the machine IP. |
| `--retry-for SECONDS` | `600` | With `--wait`: keep retrying the spawn for up to this long. |
| `--interval SECONDS` | `15` | With `--wait`: base delay between spawn attempts (jittered ±20%) and between IP-availability polls. |

Modes:

- `play` — `POST /machine/play/{id}`, used for playable machines.
- `spawn` — `POST /vm/spawn`, used for retired and VIP machines.
- `auto` — tries `play` first and falls back to `spawn` when the API
  rejects it (HTTP 400, 404, 409, or 422).

#### Peak times and seasonal releases

When a seasonal machine drops (Saturdays 19:00 UTC), spawn capacity fills
instantly and `/vm/spawn` rejects requests until slots free up; machines
that do spawn can take a while to receive an IP. `--wait` handles both:

- Capacity rejections (HTTP 429/500/502/503/504, or messages mentioning
  full/busy/capacity/try-again) are retried for up to `--retry-for`
  seconds, with a ±20% jitter on `--interval` so simultaneous clients do
  not retry in lockstep. Non-transient errors (401, 404, ...) still fail
  immediately.
- After a successful spawn, the command polls the active machine until an
  IP is assigned (up to `--retry-for` seconds, at the `--interval` cadence),
  then prints the id, name, and IP.

```bash
# Fire this right at the release moment and walk away:
htb machine start Seasonal --wait --retry-for 900

# Tighter cadence: retry for 6 minutes, polling every 5 seconds.
htb machine start Nimbus --mode auto --wait --retry-for 360 --interval 5
```

### machine stop

Stop a machine. Without a target, stops the currently active machine.

```bash
htb machine stop
htb machine stop BoardLight
```

| Argument | Description |
| --- | --- |
| `target` | Optional machine id or name. Defaults to the active machine. |

Endpoint: `POST /vm/terminate`

### machine reset

Reset a machine. Without a target, resets the currently active machine.

```bash
htb machine reset
htb machine reset 444
```

| Argument | Description |
| --- | --- |
| `target` | Optional machine id or name. Defaults to the active machine. |

Endpoint: `POST /vm/reset`

### machine extend

Extend a machine's expiry, buying more time before it is reaped. Without a
target, extends the currently active machine.

```bash
htb machine extend
htb machine extend BoardLight
```

| Argument | Description |
| --- | --- |
| `target` | Optional machine id or name. Defaults to the active machine. |

Endpoint: `POST /vm/extend`

### machine submit

Submit a user or root flag. HTB infers user versus root from the flag itself.

```bash
htb machine submit 444 'HTB{...}' --difficulty 50
htb machine submit BoardLight "$(cat user.txt)" --difficulty 40
```

| Argument / option | Description |
| --- | --- |
| `target` | Machine id or name. |
| `flag` | The flag value. Quote it to protect shell metacharacters. |
| `--difficulty N` | Required difficulty rating from 10 (piece of cake) to 100 (brainfuck), in steps of 10. |

Endpoint: `POST /machine/own`

---

## challenge

Challenges live on their own endpoints, separate from machines:

- `GET /api/v4/challenges` is a paginator. `htb` walks it with `per_page=100`
  and stops at the last page, at a repeated page, or when `--limit` is reached.
- A challenge file is served as a `302` to a presigned S3 URL, so the archive
  download sends the bearer token for the API hop and **no** `Authorization`
  header for the storage hop. S3 answers `400 InvalidArgument` ("Only one auth
  mechanism allowed") if the token rides along.
- A container challenge needs a started instance before its ports answer.

List pages are cached for five minutes under
`~/.config/htb-terminal/cache/`. When the API answers HTTP 429 after the client
has exhausted its backoff (1s, 2s, 4s, 8s, honoring `Retry-After`), the cached
page is served with a warning instead of the command failing. Pass `--no-cache`
to refetch.

### challenge list

```bash
htb challenge list
htb challenge list --state active --difficulty easy --limit 5
htb challenge list --state active --limit 5
htb challenge list --difficulty very-easy --category Web
htb challenge list --unowned --difficulty medium --search crypto --limit 10
htb --json challenge list --state active --all
```

| Option | Default | Description |
| --- | --- | --- |
| `--state {active,retired,retired_free}` | all | Sent to the API as the `state` filter. |
| `--difficulty {very-easy,easy,medium,hard,insane}` | all | Sent to the API as the `difficulty[]` filter. `very easy` and `very_easy` are normalized, so quoting "very easy" works. |
| `--category NAME` | all | Category name such as `Web`, `Reversing`, `Crypto`, `Forensics`, `Pwn`. Matched case-insensitively. The endpoint has no category-name parameter, so this is applied locally. |
| `--owned` / `--unowned` | both | Filter on `is_owned` (the field the API returns). Applied locally. |
| `--search TEXT` | — | Case-insensitive substring match on the name, or an exact id. Applied locally. |
| `--limit N` | `20` | Maximum rows to print. Paging stops as soon as the limit is met. |
| `--all` | off | Print every match, ignoring `--limit`. |
| `--no-cache` | off | Refetch pages instead of serving the five-minute page cache. |

Filtering that the API does not support runs locally, and if the API ever
rejects the server-side filters (HTTP 400/422), the command warns and filters
everything locally rather than failing.

Columns: `id`, `name`, `category`, `difficulty`, `state`, `solves`, `owned`.

`--json` prints a machine-readable envelope, not a bare list:

```json
{
  "challenges": [{"id": 883, "name": "Broken Shell", "category": "Misc",
                  "difficulty": "Easy", "state": "active", "solves": 1407,
                  "owned": true, "rating": 4.8}],
  "count": 1,
  "meta": {"pages_scanned": 1, "cached_pages": 0, "truncated": false,
           "page_cap_reached": false, "limit": 20}
}
```

Endpoint: `GET /challenges?page=N&per_page=100[&state=...][&difficulty[]=...]`

### challenge info

```bash
htb challenge info 883
htb --json challenge info 883
```

The summary shows the name, category, difficulty, state, points, solves,
`play_methods`, the challenge file (name and size), `play_info` (`status`, `ip`,
`ports`, `expires_at`, `expires_in`), and the description. A container
challenge with nothing running reports `play_info: status not running` instead
of hiding the block. `--json` prints the raw `/challenge/info/<id>` payload.

Endpoint: `GET /challenge/info/<id>`

### challenge download

```bash
htb challenge download 806
htb challenge download 806 --extract
htb challenge download 806 -o /tmp/ch806.zip --extract
htb challenge download 806 -o downloads/          # -> downloads/ch806.zip
htb challenge download 806 --extract --password <word>
```

| Option | Default | Description |
| --- | --- | --- |
| `-o, --out PATH` | `challenges/ch<id>/ch<id>.zip` | Archive path, or a directory (an existing directory or a path without a suffix) to drop `ch<id>.zip` into. |
| `--extract` | off | Extract next to the archive, after verifying the file is a zip. |
| `--password VALUE` | HTB's published archive word | Archive password used by `--extract`. Recent challenges may use another word; it is printed on the challenge page. |

The archive is validated with a zip check before extraction, and members that
would escape the destination directory are rejected (this is reported as
such, not as a password problem). Extraction is also refused when the archive
would expand beyond 4 GiB. A wrong password is reported with a pointer to
`--password`.

The download flow is: `GET /challenge/download/<id>` → read the `302`
`Location` without following it (anything but an `https` URL is refused) →
`GET` that presigned URL **without** the bearer token → save. Results are printed as `output`, `size`, `size_human`,
and, with `--extract`, `extracted_to` and `files`.

### challenge start

```bash
htb challenge start 883
htb challenge start 883 --wait 300 --interval 5
htb challenge start 1520 --force
```

`start` posts `POST /container/start` with `{"challenge_id": id}`, then polls
`GET /challenge/info/<id>` until `play_info.status == "ready"` and an IP is
assigned. That field is null for the first 30-90 seconds, so the poll is
expected; progress goes to stderr. When ready, it prints `status`, `ip`,
`ports`, `expires_at`, `expires_in`, and the server message.

| Option | Default | Description |
| --- | --- | --- |
| `--wait SECONDS` | `180` | How long to poll for a ready container. |
| `--interval SECONDS` | `5` | Poll interval while the container boots. |
| `--force` | off | Stop the tracked running container first, then start this one. |

#### Single container rule

**HTB allows one challenge container per account, and starting a second one
silently kills the first** — there is no error, the existing `host:port` just
stops accepting connections. Because the API cannot list running containers,
`htb` tracks what it started in
`~/.config/htb-terminal/containers.json` (mode `0600`):

- `challenge start` refuses while another challenge is tracked as running, and
  names it, so a live instance is never orphaned by accident.
- `--force` stops the tracked container first (freeing the slot), then starts
  the new one.
- Tracked entries expire on their own: once `expires_at` has passed, the entry
  no longer blocks a start, so a crashed session does not wedge the CLI.

Endpoints: `POST /container/start`, `POST /container/stop`

### challenge stop

```bash
htb challenge stop 883
htb challenge stop          # the tracked running container
```

Posts `POST /container/stop` with `{"challenge_id": id}` and clears the tracked
entry.

### challenge status

```bash
htb challenge status
htb challenge status 883
htb --json challenge status
```

Lists tracked containers with their live `status`, `ip`, `ports`, and time to
expiry (`in 2h 59m`, or `expired`). Each row is refreshed from
`GET /challenge/info/<id>` when the API answers, and falls back to the tracked
values when it does not.

| Column | Description |
| --- | --- |
| `id` | Challenge id. |
| `name` | Challenge name, when the API answered. |
| `status` | `play_info.status` (`ready`, `deploying`, ...). |
| `ip` | Instance IP. |
| `ports_text` | Comma-separated ports (also available as a `ports` list in `--json`). |
| `expires` | Time to expiry, relative to now. |

`--json` prints `{"containers": [{"id": ..., "ports": [...], "expires": "in 2h 59m", "tracked": true, ...}]}`.

### challenge own

```bash
htb challenge own 883 --flag 'HTB{...}'
htb --json challenge own 883 --flag 'HTB{...}'
```

Posts `POST /challenge/own` with `{"challenge_id": id, "flag": flag}` and prints
the server message. `Congratulations!` means it counted; a rejection such as
`Incorrect flag` is printed to stderr as `error: ...` and the command exits
non-zero (1), so scripts can branch on the exit code.

---

## sherlock

Sherlocks are the task-based DFIR challenges. Each one has numbered tasks that
are answered with graded strings. The list and info payloads do not carry the
tasks — they come from `GET /sherlocks/<id>/tasks` — and progress is a separate
call.

### sherlock list

```bash
htb sherlock list
htb sherlock list --active --limit 10
htb sherlock list --difficulty easy --unowned
htb --json sherlock list --active
```

| Option | Default | Description |
| --- | --- | --- |
| `--active` | off | Only the active Sherlocks (sent as `state=active`). |
| `--difficulty {very-easy,easy,medium,hard,insane}` | all | Sent to the API as the `difficulty[]` filter. |
| `--owned` / `--unowned` | both | Filter on `is_owned`. Applied locally. |
| `--search TEXT` | — | Name substring or exact id. Applied locally. |
| `--limit N` | `20` | Maximum rows to print. |
| `--all` | off | Print every match, ignoring `--limit`. |
| `--no-cache` | off | Refetch pages instead of using the five-minute page cache. |

Columns: `id`, `name`, `difficulty`, `state`, `solves`, `owned`, `progress`.

`--json` prints `{"sherlocks": [...], "count": N, "meta": {...}}` with the same
`meta` keys as `challenge list`.

Endpoint: `GET /sherlocks?page=N&per_page=100[&state=...][&difficulty[]=...]`

### sherlock tasks

```bash
htb sherlock tasks 631
htb sherlock tasks 631 --hints
htb --json sherlock tasks 631
```

Lists each task's `id`, `title`, `question` (`description`), `answer_format`
(`masked_flag`), `completed`, and `prerequisite_id`. Hints are excluded by
default; `--hints` adds them. If the API returns no tasks for the id, the
command says so explicitly rather than inventing fields.

`--json` prints `{"sherlock_id": 631, "count": 8, "tasks": [...]}`.

Endpoint: `GET /sherlocks/<id>/tasks`

### sherlock answer

```bash
htb sherlock answer 631 2880 '10.0.0.5'
htb --json sherlock answer 631 2880 '10.0.0.5'
```

Posts `POST /sherlocks/<id>/tasks/<task_id>/flag` with `{"flag": answer}`.
The outcomes are surfaced distinctly:

| Result | Output | Exit code |
| --- | --- | --- |
| `200` / `201` | The server message (accepted). | `0` |
| `400` | `error: Wrong answer for task <id>: ...` | `1` |
| `403` | `error: Task <id> is locked or not available ...` plus the prerequisite hint. | `1` |
| `404` | `error: Sherlock <id> has no task <task_id>` plus the `htb sherlock tasks <id>` hint. | `1` |

### sherlock progress

```bash
htb sherlock progress 631
htb --json sherlock progress 631
```

Shows `answered`, `total`, `progress` (percentage), `owned`, and `own_rank`.

Endpoint: `GET /sherlocks/<id>/progress`

---

## vpn

VPN commands accept a server target as a numeric id, a known alias, or a
friendly server name from the live listing. The name is matched
case-insensitively against the `name` column of `htb vpn servers`.

### vpn servers

List the VPN servers your account can use, fetched live from the API.
Includes VIP and VIP+ pools when your subscription covers them. Without
an argument, lists the `labs` product (regular machines).

```bash
htb vpn servers                # labs (default)
htb vpn servers starting_point
htb vpn servers --static       # offline alias table only
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `product` | `labs` | Optional positional. Which server pool to list: `labs`, `starting_point`, `competitive`, `fortresses`, `release_arena`. |
| `--static` | off | Skip the API and show only the built-in offline aliases. |

Columns: `id`, `name`, `group`, `location`, `clients`, `full`, `assigned`.
The assigned server sorts first. When the live fetch fails, falls back to
the static alias table automatically. `--static` needs no token and makes no
network request.

A successful live response with no servers remains empty; it does not show
static aliases as if they were available in the requested pool.

Endpoint: `GET /connections/servers?product=<product>`

Built-in aliases (always available, also shown with `--static`):

| Alias | Id | Scope | Location |
| --- | --- | --- | --- |
| `eu-sp-1` | 412 | starting-point | EU |
| `us-sp-1` | 414 | starting-point | US |
| `eu-free-1` | 1 | machines | EU |
| `eu-free-2` | 201 | machines | EU |
| `eu-free-3` | 253 | machines | EU |
| `us-free-1` | 113 | machines | US |
| `us-free-2` | 202 | machines | US |
| `us-free-3` | 254 | machines | US |
| `au-free-1` | 177 | machines | AU |
| `sg-free-1` | 251 | machines | SG |

### vpn switch

Switch your account to a VPN server.

```bash
htb vpn switch us-free-1
htb vpn switch 254
htb vpn switch 'EU Machines VIP+ 1'
```

| Argument | Description |
| --- | --- |
| `server` | Server id, alias, or live server name. |

Endpoint: `POST /connections/servers/switch/{id}`

### vpn download

Download an OVPN file for a server.

```bash
htb vpn switch us-free-1
htb vpn download us-free-1
htb vpn download eu-free-2 -o configs/eu.ovpn --variant 1
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `server` | -- | Server id, alias, or live server name. |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. Parent directories are created. |
| `--variant N` | `0` | OVPN variant. `0` is UDP; other values select alternative protocols when HTB offers them (for example TCP). |

Endpoint: `GET /access/ovpnfile/{id}/{variant}`

HTB serves the configuration only for the account's currently assigned VPN
server. Run `vpn switch` first, or use `vpn connect`, which switches before it
downloads.

Downloaded VPN configurations are written with owner-only permissions on
platforms that support POSIX file modes, and symlink output files are refused
where the operating system supports that protection.

### vpn connect

Check that a server is selectable, switch to it, download its OVPN file, then
run OpenVPN with it. Prints the exit code on success and reports an error
with a failing CLI exit status when OpenVPN exits unsuccessfully.

```bash
htb vpn connect us-free-1
htb vpn connect eu-free-1 -o lab-vpn.ovpn --openvpn-command "sudo openvpn"
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `server` | -- | Server id, alias, or live server name. |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. |
| `--variant N` | `0` | OVPN variant. |
| `--openvpn-command CMD` | `sudo openvpn` | Command to run; `--config <file>` is appended. |

OpenVPN needs root to create the tun interface. When the CLI is not running as
root, the OpenVPN command must be wrapped in `sudo`, `doas`, or `pkexec` (the
default already uses `sudo`); otherwise `vpn connect` aborts before switching
servers. This keeps token handling and API requests unprivileged.

---

## user

### user info

Show your own HTB profile: rank, points, and owns. Resolves your user id from
`GET /user/info`, then fetches the basic profile.

```bash
htb user info
htb --json user info
```

With the global `--json` flag, the full basic profile is printed instead of the
summary.

Endpoints: `GET /user/info`, `GET /user/profile/basic/{id}`

---

## completion

Print a shell completion script for `htb` and `htbx`.

```bash
eval "$(htb completion bash)"   # bash
eval "$(htb completion zsh)"    # zsh
```

| Argument | Description |
| --- | --- |
| `shell` | One of `bash`, `zsh`. |

This command makes no network calls and needs no token.

---

## speedrun

One-shot season-release flow for when a seasonal machine drops and spawn
capacity fills instantly. It runs these steps with a live, emoji-free status
line for each:

1. Resolve the machine id.
2. Check the server against live selectable options, switch your account to it,
   and download its OVPN file.
3. Start OpenVPN and wait for the tunnel interface to come up.
4. Set the interface MTU (default 1300).
5. Spawn the machine, retrying capacity rejections (same logic as
   `machine start --wait`).
6. Wait for the machine IP and print it.

The VPN then runs in the foreground; press Ctrl-C to disconnect. Ctrl-C and
HTB API failures during setup also disconnect and reap OpenVPN automatically.
While retrying the spawn and waiting for the machine IP, `speedrun` verifies
that both OpenVPN and the tunnel interface remain active.

`speedrun` and `vpn connect` reject servers missing from the live selectable
options before switching your account. A stale assigned server is not sufficient.
HTB can still disable a server between this check and config generation; that
failure includes recovery instructions. List current servers with `htb vpn servers`
and rerun with another server ID or name. Product filters can return the same
server pool, depending on HTB availability and account access; a `release_arena`
listing does not guarantee a dedicated release server. No OpenVPN process or
machine spawn is started when config generation fails. A nonzero OpenVPN exit
causes both `speedrun` and `vpn connect` to exit with an error.

```bash
sudo "$(command -v htb)" speedrun Seasonal us-free-1
sudo "$(command -v htb)" speedrun 478 us-free-1 --mtu 1280 --retry-for 1200
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `target` | -- | Machine id or name. |
| `server` | -- | VPN server id, alias, or live server name (see `htb vpn servers`). |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. A sibling `.log` holds OpenVPN output. |
| `--variant N` | `0` | OVPN variant. |
| `--interface NAME` | `tun0` | Tunnel interface to tune. |
| `--mtu N` | `1300` | MTU to set on the interface. |
| `--mode {auto,play,spawn}` | `auto` | Which start endpoint to use. |
| `--retry-for SECONDS` | `900` | Keep retrying the spawn for up to this long. |
| `--interval SECONDS` | `15` | Base delay between spawn attempts (jittered ±20%). |
| `--openvpn-command CMD` | `openvpn` | OpenVPN command; `--config <file>` is appended. |

`speedrun` currently requires Linux, OpenVPN, and the `ip` command from
iproute2. Verify them with `command -v openvpn ip`, and run `sudo -v` before a
time-sensitive release if you want to cache sudo authentication. The downloaded
configuration and sibling OpenVPN log are owner-only and refuse symlink targets
where supported. It uses the same endpoints as `vpn switch`, `vpn download`,
and `machine start`.

---

## raw

Call any Labs v4 endpoint directly with your token. Useful for endpoints not
wrapped by a dedicated command.

```bash
htb raw GET /machine/active
htb raw GET /machine/profile/444
htb raw POST /vm/spawn --data '{"machine_id":478}'
htb raw GET /access/ovpnfile/1/0 -o lab-vpn.ovpn
```

| Argument / option | Description |
| --- | --- |
| `method` | One of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `path` | Endpoint path such as `/machine/active`. The leading slash is optional. |
| `--data JSON` | JSON request body for write requests. |
| `-o, --output PATH` | Write the raw response body to a file instead of printing it. Useful for binary responses. |

JSON responses are pretty-printed; non-JSON responses are printed as text.
With `-o`, the status code and output path are printed instead.

## Pro Labs and Fortresses

Both products are separate from machines and challenges, and both are reached over
their own VPN profile (`htb vpn`). Neither is spawnable from this client.

| command | endpoint | notes |
| --- | --- | --- |
| `htb prolab list` | `GET /prolabs` | machines/flags counts, state (`free`/`paid`), release date |
| `htb prolab machines <id>` | `GET /prolab/<id>/machines` | machine ids, names, OS |
| `htb fortress list` | `GET /fortresses` | flag counts and owned progress |
| `htb fortress info <id>` | `GET /fortress/<id>` | points, ip, company, per-flag points and owned state |

There is no `/prolab/<id>` detail route (it answers 404) and no per-fortress
machines route, so the list payload is the only source of lab metadata. Fortress
scoring is by named flags, not user/root pairs: `fortress info` prints each flag
with its points and a `points: earned/total` line.

## Progress and submissions

| command | endpoint |
| --- | --- |
| `htb progress show` | `/user/info` + `/profile/progress/{machines,challenges,fortress,prolab}/<id>` |
| `htb progress show machines\|challenges\|fortress\|prolab` | one category |
| `htb progress submissions machines\|challenges` | `/user/submissions/<kind>` |
| `htb progress connection` | `/user/connection/status` |

The per-OS route (`/profile/progress/machines/os/<id>`) documented in the public
Postman collection now answers 404; the aggregate `machines` route carries the
same solved/total numbers.

`prolab` also gained `info` (`/prolab/<id>/info`) and `flags`
(`/prolab/<id>/flags`, with owned/total points).

## Flag submission and activity

| command | endpoint | notes |
| --- | --- | --- |
| `htb fortress own <id> --flag` | `POST /fortress/<id>/flag` | body `{"flag": ...}`; 400 `Wrong flag` on a miss |
| `htb prolab own <id> --flag` | `POST /prolab/<id>/flag` | 400 `Incorrect flag` on a miss |
| `htb machine activity <id>` | `GET /machine/activity/<id>` | owns and bloods, newest first |
| `htb machine walkthroughs <id>` | `GET /machine/walkthroughs/<id>` | 400 unless the box is retired |
| `htb challenge activity <id>` | `GET /challenge/activity/<id>` | 404 for an unknown id |

`machine list` also takes `--difficulty` and `--os`. Those are **local** filters:
unlike `challenge list`, the machine list endpoints accept no such query
parameters, so they apply to the page that was fetched.
