#!/usr/bin/env python3
"""Command-line client for the self-hosted SMS gateway.

Talks to the running server over HTTP so the queue and rate limits stay
centralized. Credentials and host/port are read from the same .env file.

Examples:
    python cli.py send +15551234567 "Hello from my phone"
    python cli.py status
"""

from __future__ import annotations

import argparse
import sys

import httpx

from app.config import get_settings


def _base_url(settings) -> str:
    host = settings.server_host
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{settings.server_port}"


def _auth(settings):
    return (settings.server_username, settings.server_password)


def cmd_send(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        resp = httpx.post(
            f"{_base_url(settings)}/send",
            json={"recipient": args.recipient, "message": args.message},
            auth=_auth(settings),
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        print(f"error: could not reach server: {exc}", file=sys.stderr)
        return 1

    if resp.status_code == 401:
        print("error: bad SERVER_USERNAME/SERVER_PASSWORD", file=sys.stderr)
        return 1
    if resp.status_code >= 400:
        print(f"error: HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    print(
        f"queued message #{data['id']} "
        f"(queue length: {data['queue_position']})"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        resp = httpx.get(
            f"{_base_url(settings)}/status",
            auth=_auth(settings),
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        print(f"error: could not reach server: {exc}", file=sys.stderr)
        return 1

    if resp.status_code >= 400:
        print(f"error: HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    d = resp.json()
    print(f"Queue length ........... {d['queue_length']}")
    print(f"Sent today ............. {d['sent_today']}")
    print(f"Daily limit ............ {d['daily_limit']}")
    print(f"Remaining quota ........ {d['remaining_daily_quota']}")
    print(f"Min interval (s) ....... {d['min_interval_seconds']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SMS gateway CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_send = sub.add_parser("send", help="queue a message to send")
    p_send.add_argument("recipient", help="phone number, e.g. +15551234567")
    p_send.add_argument("message", help="message text")
    p_send.set_defaults(func=cmd_send)

    p_status = sub.add_parser("status", help="show queue/quota status")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
