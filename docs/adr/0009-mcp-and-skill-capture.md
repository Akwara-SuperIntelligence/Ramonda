# 0009 — Deferred: MCP and skill capture

Status: deferred. Not built. Documented so they are not lost.

## MCP

**What.** Model Context Protocol servers expose tools. The model would discover
tools at runtime instead of using the fixed registry.

**Why deferred.** MCP adds a trust boundary. A third-party server supplies tool
names, schemas, and results. It can change them. It needs authentication,
an allowlist per org, schema validation, timeouts, audit, and a way to pin a
tool set per turn so the prompt does not change mid-conversation. The secret
broker does not exist yet.

**What it needs.** A tool catalog, an allowlist, schema validation, a secret
lease per server, audit, and a stable tool pin per turn.

**Decision.** Not adopted now. Keep the fixed registry. Revisit when a customer
needs a third-party tool and the secret broker exists.

## Skill capture ("learn by watching")

**What.** Record a human's steps in the sandbox, summarise them, propose a
`SKILL.md`, let a human approve it, and store it in the skill files.

**Why deferred.** It needs the sandbox to record a screen or a session, a
summariser to write the skill, and a review step so a poisoned session cannot
become a trusted skill. It also needs the skill store, which depends on the
memory decision.

**What it needs.** Session recording, a summariser, a skill writer, human
approval, provenance, versioning, and deletion.

**Decision.** Deferred. It has no owner until the sandbox exists and skill
storage is decided.

## Consequences

- The tool registry stays fixed and reviewed.
- Skills stay read-only for the agent.
- Both are linked from EDA and STATUS.
