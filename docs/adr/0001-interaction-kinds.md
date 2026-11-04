# 0001 — Interaction kinds

Status: accepted. Action approvals and the choice data contract are built.
Permission approvals, choice card rendering, and custom rules are not.

## Context

The service has several ways to ask a human for something. They were being
mixed into one idea called "approval". They are not the same:

- A choice asks a question with options. It does not gate an effect.
- An action approval gates one irreversible effect.
- A permission approval grants a capability for a scope and a duration.
- An auto-review is a model filter before the human gate.
- A custom rule is a standing instruction.

The screenshots in the design discussion show all of these. Two rules follow:
do not build a separate card per tool, and do not forget the deferred kinds.

## Decision

One typed payload, discriminated by `kind`. The agent service owns the schema.
The client owns the rendering. Per-tool differences are data, not client code.

An action approval payload:

```json
{
  "kind": "action",
  "title": "Send email?",
  "action": "send_email",
  "arguments": "sarah@example.com Happy birthday",
  "fields": [
    {"key": "to", "label": "To", "value": "sarah@example.com", "editable": true},
    {"key": "message", "label": "Message", "value": "Happy birthday", "editable": true, "multiline": true}
  ],
  "consequences": "The recipient will receive this now.",
  "decisions": ["approve", "edit", "deny"],
  "review": {"verdict": "allow", "reason": "safe"}
}
```

The client walks `fields` and `decisions`. It does not know what `send_email`
is. The terminal client prints the card. A Slack or web client draws it.

## Kinds

| Kind | Gates an effect | Decisions | Needs |
|---|---|---|---|
| `action` | Yes, one effect | approve, edit, deny | Nothing new |
| `permission` | Yes, a capability | allow once, always allow, never | Sandbox and a policy store |
| `choice` | No | pick one option | A client that renders options |
| `review` | No, runs before the gate | allow, deny, escalate | Nothing new |
| `rule` | No, it is policy | create, change, remove | A policy store |

### action

One irreversible effect. The payload has typed fields, a draft, consequences,
and the reviewer verdict. The human approves, edits, or denies. The approval is
single-use and has a 10-minute deadline. An edit replaces the arguments before
the effect runs. The approval stays single-use.

### permission

A capability, not one action: "allow this bot to run commands on this computer".
It needs a scope, a duration, and a policy store. "Always allow" is a rule, not
an approval row. This kind waits for the sandbox and the policy store.

### choice

A question with options. It is not a gate. The data contract is the `options`
field on `agent.message.composed`. The next user message is the answer. The
tappable card needs a client. The terminal prints the options as text.

### review

A second model reads a proposed action before the human gate. It answers
`allow`, `deny`, or `escalate`. Deny becomes a tool result. Escalate goes to the
human. A reviewer failure escalates; it does not block the action. The review
is a filter, not a guarantee.

### rule

A standing instruction, for example "never delete anything". It needs a policy
store and an owner. It is not a card and not a one-off approval.

## Consequences

- Event payloads stay additive. `kind` lets new interactions arrive without a
  new event type.
- The client renders by `kind` and `fields`. No per-tool cards.
- The agent service does not know how a client draws a card.
- Permission approvals and custom rules are blocked on the sandbox and a policy
  store, not on this schema.
- The choice card UI is blocked on channels, not on the agent service.

## Open

- The permission scope model: per machine, per folder, per tool, or per site.
- Whether a choice needs a structured reply event, or the next message is enough.
- Where custom rules live and who can change them.
