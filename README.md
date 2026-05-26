# htb-terminal

Python terminal client for selected HTB Labs v4 API workflows:
machines, VPN, OVPN files, and raw API calls.

## Sources

- Official HTB Enterprise Public API documentation: https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api
- Official HTB article on Lab/OpenVPN access: https://help.hackthebox.com/en/articles/5185687-gs-introduction-to-lab-access
- v4 Postman collection provided in the request: https://documenter.getpostman.com/view/13129365/TVeqbmeq
- Readable community reference for Labs v4 endpoints: https://github.com/D3vil0p3r/HackTheBox-API

Note: HTB officially documents the Enterprise API. The Labs v4 endpoints used here come from the Postman collection and community references; they may change without notice.

## Screenshots

Compact active-machine output keeps the session details and profile-only status text readable without dumping the full HTB profile.

![Active machine output](docs/screenshots/machine-active.png)

Tables use compact columns, terminal colors, and truncation by default. Use `--wide` when you need full values.

![VPN server table output](docs/screenshots/vpn-servers.png)

## Installation

This project has no external dependencies.

```bash
chmod +x ./htb
./htb --help
```

By default, the token is read from `api.token` in the current directory. You can also use:

```bash
export HTB_API_TOKEN="..."
```

## Examples

```bash
./htb machine active
./htb machine profile "BoardLight"
./htb machine list
./htb machine list --retired --page 1
./htb machine list --sp-tier 1
./htb machine search board
./htb machine search kerberos --all --limit 10
./htb machine search "breach creds" --all --profiles

./htb machine start "BoardLight" --mode auto
./htb machine start 444 --mode play
./htb machine start 478 --mode spawn
./htb machine stop
./htb machine reset
./htb machine submit 444 HTB{flag} --difficulty 50

./htb vpn servers
./htb vpn switch us-free-1
./htb vpn download us-free-1 -o lab-vpn.ovpn
./htb vpn connect us-free-1 -o lab-vpn.ovpn

./htb raw GET /machine/active
./htb raw POST /vm/spawn --data '{"machine_id":478}'
```

## Output

By default, commands print human-readable output with terminal-width wrapping and automatic color when stdout is an interactive terminal.

Use raw JSON for scripts:

```bash
./htb --json machine active
```

Color can be controlled globally:

```bash
./htb --color never machine active
./htb --color always machine list
```

Tables are compact by default and truncate long cells to fit common terminal widths. Use `--wide` to keep full table values:

```bash
./htb --wide machine list
./htb --wide machine search active-directory --all
```

`machine active` enriches the active session response with the matching machine profile when a machine is active, but prints a compact summary by default. The summary includes useful profile-only text such as `info_status` and `description` when HTB returns it. Use `--details` for synopsis and Academy module names, or `--json` before the command for the full enriched response:

```bash
./htb machine active --details
./htb --json machine active
```

## Machine search

`machine search` intentionally uses the documented/listed Labs v4 machine list endpoints and filters the results locally. It does not depend on an undocumented search endpoint.

By default it scans playable machines:

```bash
./htb machine search linux
```

Useful options:

- `--retired`: search retired machines only.
- `--all`: search playable and retired machines.
- `--profiles`: also fetch each scanned machine profile and search profile-only fields such as descriptions.
- `--limit N`: stop after printing up to `N` matches.
- `--max-pages N`: cap the number of API pages scanned per list.

Without `--profiles`, the query matches machine id, name, OS, difficulty, tags, maker names, and common list fields. Use `--profiles` for terms that may only exist in the detailed machine profile, for example description text mentioning breached credentials.

## Architecture

- `htb_terminal/config.py`: loads the token and API URL.
- `htb_terminal/http.py`: authenticated HTTP client.
- `htb_terminal/services/machines.py`: machine operations.
- `htb_terminal/services/vpn.py`: VPN and OVPN operations.
- `htb_terminal/cli.py`: CLI parsing and orchestration.

Each module keeps a single responsibility to make future changes easier if HTB changes an endpoint.
