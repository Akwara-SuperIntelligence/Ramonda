"""Create and manage routines from the terminal. Operator only.

Sources
    EDA §4.3 — UpdateRoutine creates or changes a Temporal Schedule
    talk §03 — a routine is a trigger

Delta
    CLI-only until commands are authenticated. Each routine is a row plus a
    Temporal Schedule; this tool writes both.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from temporalio.service import RPCError

from agent_service import routines


async def _create(args) -> str:
    return await routines.create_routine(
        args.org, args.conversation, args.cron, args.text, args.timezone
    )


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="manage agent routines")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a schedule")
    create.add_argument("--org", required=True)
    create.add_argument("--conversation", required=True)
    create.add_argument("--cron", required=True, help='for example "0 8 * * *"')
    create.add_argument("--text", required=True, help="what the routine asks the agent")
    create.add_argument("--timezone", default="UTC")

    listing = sub.add_parser("list", help="list routines")
    listing.add_argument("--org", required=True)
    listing.add_argument("--conversation")

    for name, help_text in (
        ("pause", "pause a schedule"),
        ("resume", "resume a schedule"),
        ("delete", "delete a schedule"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("routine_id")

    args = parser.parse_args()
    try:
        if args.command == "create":
            routine_id = asyncio.run(_create(args))
            print(routine_id)
        elif args.command == "list":
            rows = asyncio.run(routines.list_routines(args.org, args.conversation))
            print(json.dumps(rows, indent=2, default=str))
        elif args.command == "pause":
            asyncio.run(routines.set_enabled(args.routine_id, False))
            print(f"paused: {args.routine_id}")
        elif args.command == "resume":
            asyncio.run(routines.set_enabled(args.routine_id, True))
            print(f"resumed: {args.routine_id}")
        else:
            asyncio.run(routines.delete_routine(args.routine_id))
            print(f"deleted: {args.routine_id}")
    except (ValueError, RPCError) as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main_cli()
