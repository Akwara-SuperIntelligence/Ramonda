"""The event envelope: the contract between services.

Sources
    EDA §4.1 — the envelope fields and their rules
    talk §03 — an event is what wakes the agent

Delta
    The first working contract. Consumers ignore unknown fields, so this
    dataclass only names what it reads.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

SEND_MESSAGE = "agent.command.send_message"
MESSAGE_COMPOSED = "agent.message.composed"
MESSAGE_TOPIC = "agent.messages"


@dataclass
class Envelope:
    event_id: str
    type: str
    org_id: str
    subject: dict
    payload: dict
    version: int = 1
    occurred_at: str = ""
    actor_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    priority: str = "interactive"
    traceparent: str = ""

    @classmethod
    def from_json(cls, raw: bytes) -> Envelope:
        data = json.loads(raw)
        missing = {"event_id", "type", "org_id", "subject", "payload"} - data.keys()
        if missing:
            raise ValueError(f"envelope missing {sorted(missing)}")
        return cls(
            event_id=data["event_id"],
            type=data["type"],
            org_id=data["org_id"],
            subject=data["subject"],
            payload=data["payload"],
            version=data.get("version", 1),
            occurred_at=data.get("occurred_at", ""),
            actor_id=data.get("actor_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            priority=data.get("priority", "interactive"),
            traceparent=data.get("traceparent", ""),
        )

    def to_json(self) -> bytes:
        return json.dumps(asdict(self)).encode()
