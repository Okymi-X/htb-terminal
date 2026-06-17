# htb-terminal

[![CI](https://github.com/Okymi-X/htb-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/Okymi-X/htb-terminal/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Python terminal client for selected HTB Labs v4 API workflows:
machines, VPN, OVPN files, and raw API calls. Zero external dependencies.

See the [command reference](docs/commands.md) for every command, option,
default, and the API endpoint each command calls.

## Sources

- Official HTB Enterprise Public API documentation: https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api
- Official HTB article on Lab/OpenVPN access: https://help.hackthebox.com/en/articles/5185687-gs-introduction-to-lab-access
- v4 Postman collection: https://documenter.getpostman.com/view/13129365/TVeqbmeq
- Readable community reference for Labs v4 endpoints: https://github.com/D3vil0p3r/HackTheBox-API

Note: HTB officially documents the Enterprise API. The Labs v4 endpoints used here come from the Postman collection and community references; they may change without notice.

## Screenshots

Compact active-machine output keeps the session details and profile-only status text readable without dumping the full HTB profile.

![Active machine output](docs/screenshots/machine-active.png)

Tables use compact columns, terminal colors, and truncation by default. Use `--wide` when you need full values.

![VPN server table output](docs/screenshots/vpn-servers.png)

## Installation

Requires Python 3.10+. This project has no external dependencies.

Install as a global command with [pipx](https://pipx.pypa.io) (recommended) so
`htb` is available from any directory:

```bash
pipx install htbx
htb --help
```

Or with pip:

```bash
pip install htbx
htb --help
```

The package is published on PyPI as **`htbx`**; it installs the `htb` command
(an `htbx` alias is installed too). To run the latest from source without
installing, use a clone:

```bash
chmod +x ./htb
./htb --help
```

### Authentication

Generate an App Token from your HTB profile settings, then save it once with
`init`:

```bash
htb init
# Paste your HTB App Token (input hidden): ...

htb init --check   # also verify the token and print who you are
```

`init` stores the token in your user config directory
(`~/.config/htb-terminal/token`, or `$XDG_CONFIG_HOME/htb-terminal/token`) with
owner-only permissions, so a pipx-installed `htb` finds it from anywhere. You
can also pass it non-interactively:

```bash
htb init --token "$MY_TOKEN"
echo "$MY_TOKEN" | htb init
```

The token is resolved in this order, first match wins:

1. `HTB_API_TOKEN` environment variable.
2. `--token-file PATH`, when given.
3. `./api.token` in the current directory (handy as a per-project override).
4. The user config file written by `htb init`.

`api.token` is gitignored; never commit your token.

## Examples

Full details for each command are in the [command reference](docs/commands.md).

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
./htb machine extend
./htb machine submit 444 HTB{flag} --difficulty 50
./htb machine active --oneline

./htb user info

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

## Shell completion

Enable tab-completion for commands, subcommands, and options. The same script
works for both the `htb` and `htbx` commands.

```bash
# bash — add to ~/.bashrc:
eval "$(htb completion bash)"

# zsh — add to ~/.zshrc (before compinit, or save to a file on your $fpath):
eval "$(htb completion zsh)"
```

## Architecture

- `htb_terminal/config.py`: loads/saves the token and API URL.
- `htb_terminal/http.py`: authenticated HTTP client.
- `htb_terminal/output.py`: human-readable and JSON rendering.
- `htb_terminal/timefmt.py`: relative time formatting for display.
- `htb_terminal/completion.py`: bash/zsh completion scripts from one command map.
- `htb_terminal/services/machines.py`: `MachineService` — machine API operations.
- `htb_terminal/services/user.py`: `UserService` — current-user profile.
- `htb_terminal/services/payloads.py`: pure helpers that reshape machine-list JSON.
- `htb_terminal/services/search.py`: local machine search and result ranking.
- `htb_terminal/services/spawn.py`: transient spawn-failure detection.
- `htb_terminal/services/vpn.py`: VPN and OVPN operations.
- `htb_terminal/cli.py`: CLI parsing and orchestration.

Each module keeps a single responsibility to make future changes easier if HTB
changes an endpoint. `MachineService` only talks to the API; payload reshaping,
search ranking, and spawn-error detection are stateless modules it composes, so
they are testable in isolation and stay small.

## Development

Install the dev tools and run the test suite:

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

The tests are also runnable with the standard library alone:

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).
