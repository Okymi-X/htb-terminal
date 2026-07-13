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

### Machine targets

Wherever a command takes a machine target, you can pass either a numeric id
(`444`) or a machine name (`BoardLight`). Names are resolved through
`/machine/profile/<name>`.

### Running with sudo / privilege elevation

Since commands like `speedrun` and `vpn connect` manage OpenVPN processes and network interfaces, they require `sudo` to run.

* **Token Resolution**: By default, `sudo` switches the environment home directory to `/root`. If a token exists at `/root/.config/htb-terminal/token`, it will be used. If not, the client automatically falls back to looking for your token under the invoking user's home config directory (retrieved using the `SUDO_USER` environment variable, e.g. `/home/username/.config/htb-terminal/token`).
* **Command Not Found (`htbx`)**: If you installed `htbx` via `pipx`, it resides in your user binary directory (e.g. `~/.local/bin`), which is not in `root`'s `PATH`. If `sudo htbx` fails with `command not found`, use `sudo htb` instead, or create a symlink to make it globally available under `/usr/bin`:
  ```bash
  sudo ln -s $(which htb) /usr/bin/htb
  ```

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

`init` makes no network calls and does not require an existing token. `Bearer`
and `Authorization:` prefixes are stripped automatically before saving.

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
the static alias table automatically.

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
htb vpn download us-free-1
htb vpn download eu-free-2 -o configs/eu.ovpn --variant 1
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `server` | -- | Server id, alias, or live server name. |
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
| `server` | -- | Server id, alias, or live server name. |
| `-o, --output PATH` | `lab-vpn.ovpn` | Where to write the OVPN file. |
| `--variant N` | `0` | OVPN variant. |
| `--openvpn-command CMD` | `sudo openvpn` | Command to run; `--config <file>` is appended. |

OpenVPN needs root to create the tun interface. When not running as root,
the command must be wrapped in `sudo`, `doas`, or `pkexec` (the default
already uses `sudo`); otherwise `vpn connect` aborts with an error before
switching servers.

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
2. Switch your account to the VPN server and download its OVPN file.
3. Start OpenVPN and wait for the tunnel interface to come up.
4. Set the interface MTU (default 1300).
5. Spawn the machine, retrying capacity rejections (same logic as
   `machine start --wait`).
6. Wait for the machine IP and print it.

The VPN then runs in the foreground; press Ctrl-C to disconnect. Ctrl-C and
HTB API failures during setup also disconnect and reap OpenVPN automatically.
While retrying the spawn and waiting for the machine IP, `speedrun` verifies
that both OpenVPN and the tunnel interface remain active.

```bash
sudo htb speedrun Seasonal us-free-1
sudo htb speedrun 478 us-free-1 --mtu 1280 --retry-for 1200
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

`speedrun` needs root to run OpenVPN and change the MTU, so run it with `sudo`.
It uses the same endpoints as `vpn switch`, `vpn download`, and `machine start`.

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
