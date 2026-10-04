"""``python -m dsh_chatgpt_bridge <command>`` — the same CLI as the standalone script."""

from .core import main

if __name__ == "__main__":
    raise SystemExit(main())
