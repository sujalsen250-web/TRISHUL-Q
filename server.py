"""TRISHUL-Q server entrypoint.

Usage:
    python server.py                 # 0.0.0.0:8000
    python server.py --host 127.0.0.1 --port 9000

The public React app (landing page + user/admin consoles) is served on the
public domain / LAN. The Super Admin panel is served at /superadmin and is
enforced localhost-only on the server side.
"""
from __future__ import annotations

import argparse

import uvicorn

from backend import config


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{config.APP_NAME} server")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print("=" * 68)
    print(f"  {config.APP_NAME}  v{config.VERSION}")
    print(f"  {config.APP_FULL_NAME}")
    print("=" * 68)
    print(f"  Public app        : http://localhost:{args.port}")
    print(f"  LAN               : http://<LAN-IP>:{args.port}")
    print(f"  Super Admin panel : http://127.0.0.1:{args.port}/superadmin   (localhost only)")
    print(f"  Database          : {config.DATABASE_URL.split('@')[-1]}")
    print("=" * 68)

    uvicorn.run("backend.main:app", host=args.host, port=args.port,
                reload=args.reload)


if __name__ == "__main__":
    main()
