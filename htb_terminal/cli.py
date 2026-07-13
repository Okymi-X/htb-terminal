"""Entry point: parse args, build a client, dispatch to a handler, render errors."""

from __future__ import annotations

import json
import sys

from htb_terminal.config import ConfigError, load_config
from htb_terminal.handlers import print_result
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        client = None
        auth_requirement = getattr(args, "needs_auth", True)
        needs_auth = auth_requirement(args) if callable(auth_requirement) else auth_requirement
        if needs_auth:
            config = load_config(token_file=args.token_file, base_url=args.base_url)
            client = HtbApiClient(config.base_url, config.token, timeout=args.timeout)
        result = args.handler(args, client)
        if result is not None:
            print_result(result, args)
        return 0
    except (ApiError, ConfigError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        # 401 means a rejected token; 403 is usually a state/permission issue
        # (e.g. "you already have an active instance"), so do not blame the token.
        if isinstance(exc, ApiError) and exc.status == 401:
            print(
                "hint: the App Token was rejected. Run 'htb init' to set a valid one,"
                " or check HTB_API_TOKEN.",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        print("interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
