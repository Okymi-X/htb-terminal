# Command reference

Complete reference for every `htb` command, including arguments, options,
defaults, and the Labs v4 endpoints each command calls.

Run `htb <command> --help` or `htb <command> <subcommand> --help` for the
built-in help at any level.

## Global options

Global options go **before** the command:

```bash
htb --json machine active
htb --color never --wide machine list
```

| Option | Default | Description |
| --- | --- | --- |
| `--version` | — | Print `htb <version>` and exit. |
| `--token-file PATH` | `api.token` | File to read the App Token from. `HTB_API_TOKEN` takes precedence when set. |
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

### Machine targets

Wherever a command takes a machine target, you can pass either a numeric id
(`444`) or a machine name (`BoardLight`). Names are resolved through
`/machine/profile/<name>`.

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
`GET /machine/todo`, `GET /machine/unreleased`, `GET /sp/tier/{tier}`

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
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `target` | — | Machine id or name. |
| `--mode {auto,play,spawn}` | `auto` | Which start endpoint to use. |

Modes:

- `play` — `POST /machine/play/{id}`, used for playable machines.
- `spawn` — `POST /vm/spawn`, used for retired and VIP machines.
- `auto` — tries `play` first and falls back to `spawn` when the API
  rejects it (HTTP 400, 404, 409, or 422).

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

## vpn

VPN commands accept either a numeric server id or one of the known aliases
listed by `htb vpn servers`.

### vpn servers

Show the known VPN server aliases as a table with columns `alias`, `id`,
`name`, `scope`, `location`.

```bash
htb vpn servers
```

Known aliases:

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

Any other server can be used by passing its numeric id directly.

### vpn switch

Switch your account to a VPN server.

```bash
htb vpn switch us-free-1
htb vpn switch 254
```

| Argument | Description |
| --- | --- |
| `server` | Server id or alias. |

Endpoint: `POST /connections/servers/switch/{id}`

### vpn download

Download an OVPN file for a server.

```bash
htb vpn download us-free-1
htb vpn download eu-free-2 -o configs/eu.ovpn --variant 1
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `server` | — | Server id or alias. |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. Parent directories are created. |
| `--variant N` | `0` | OVPN variant. `0` is UDP; other values select alternative protocols when HTB offers them (for example TCP). |

Endpoint: `GET /access/ovpnfile/{id}/{variant}`

### vpn connect

Switch to a server, download its OVPN file, then run OpenVPN with it — the
three steps in one command. Prints the OpenVPN exit code when the process
ends.

```bash
htb vpn connect us-free-1
htb vpn connect eu-free-1 -o lab-vpn.ovpn --openvpn-command "sudo openvpn"
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `server` | — | Server id or alias. |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. |
| `--variant N` | `0` | OVPN variant. |
| `--openvpn-command CMD` | `sudo openvpn` | Command to run; `--config <file>` is appended. |

OpenVPN needs root to create the tun interface. When not running as root,
the command must be wrapped in `sudo`, `doas`, or `pkexec` (the default
already uses `sudo`); otherwise `vpn connect` aborts with an error before
switching servers.

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
