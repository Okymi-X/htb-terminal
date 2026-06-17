"""Shell completion scripts, generated from one command map.

``htb completion bash`` / ``htb completion zsh`` print a script to source. The
map below is the single source of truth so completions cannot drift from the
parser.
"""

from __future__ import annotations

# command -> list of subcommands (empty list = no subcommands)
COMMANDS: dict[str, list[str]] = {
    "init": [],
    "machine": [
        "profile",
        "info",
        "active",
        "list",
        "search",
        "start",
        "stop",
        "reset",
        "extend",
        "submit",
    ],
    "vpn": ["servers", "switch", "download", "connect"],
    "user": ["info"],
    "raw": ["GET", "POST", "PUT", "PATCH", "DELETE"],
    "completion": ["bash", "zsh"],
}


def completion_script(shell: str) -> str:
    if shell == "bash":
        return _bash_script()
    if shell == "zsh":
        return _zsh_script()
    raise ValueError(f"Unsupported shell: {shell!r}. Choose bash or zsh.")


def _bash_script() -> str:
    top = " ".join(COMMANDS)
    branches = "\n".join(
        f'    {command}) COMPREPLY=( $(compgen -W "{" ".join(subs)}" -- "$cur") );;'
        for command, subs in COMMANDS.items()
        if subs
    )
    return f"""# htb bash completion. Source it or drop it in your bash completion dir.
_htb_complete() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{top}" -- "$cur") )
        return
    fi
    if [ "$COMP_CWORD" -eq 2 ]; then
        case "${{COMP_WORDS[1]}}" in
{branches}
        esac
    fi
}}
complete -F _htb_complete htb htbx
"""


def _zsh_script() -> str:
    branches = "\n".join(
        f"        {command}) compadd {' '.join(subs)};;"
        for command, subs in COMMANDS.items()
        if subs
    )
    top = " ".join(COMMANDS)
    return f"""#compdef htb htbx
# htb zsh completion. Source it or place it on your $fpath as _htb.
_htb_complete() {{
    if (( CURRENT == 2 )); then
        compadd {top}
        return
    fi
    if (( CURRENT == 3 )); then
        case $words[2] in
{branches}
        esac
    fi
}}
compdef _htb_complete htb htbx
"""
