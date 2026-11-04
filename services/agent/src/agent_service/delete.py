"""Hard-delete one conversation or one org. Operator only.

Sources
    BUILD §6.2 — the agent service owns conversation and message state
    BUILD §11 — data retention was an open decision

Delta
    No bus command. This is a local operator tool until commands are
    authenticated. It writes a row to `deletions`.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from agent_service.maintenance import delete_scope
from agent_service.routines import delete_schedules_for


async def _delete(org_id: str, conversation_id: str | None) -> dict[str, int]:
    await delete_schedules_for(org_id, conversation_id)
    return await delete_scope(org_id, conversation_id)


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="hard-delete agent data")
    parser.add_argument("--org", required=True)
    parser.add_argument("--conversation", help="omit to delete the whole org")
    parser.add_argument("--confirm", action="store_true", help="required")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("--confirm is required")
    scope = args.conversation or f"the whole org {args.org}"
    print(f"deleting {scope}", flush=True)
    try:
        counts = asyncio.run(_delete(args.org, args.conversation))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    print(json.dumps(counts, indent=2), flush=True)


if __name__ == "__main__":
    main_cli()
