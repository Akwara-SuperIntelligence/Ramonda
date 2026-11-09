# 0008 — Harness first, computer later

Status: accepted for the scope split. Memory storage, skill capture, MCP, and
long-run turns are open.

## Context

The talk lists six new model capabilities. Some need only the harness. Some need
the sandbox, which is the agent's computer and a separate service. The agent
service is the harness. It must not grow a shell or a browser of its own.

## Decision

Build harness-only capabilities now:

- helpers and sub-agents
- file and skill knowledge
- routines
- durable turns

Defer to the sandbox platform:

- `run_shell`
- `browser`
- computer use: screen, mouse, desktop
- learn by watching: record a session, then write a skill

MCP is not adopted now. The tool registry stays fixed until a decision. MCP does
not need a computer, but it is a new tool-discovery contract.

## Open

- Memory storage: the database, or files as EDA §8 says.
- Skill capture: in scope or not, and who approves a written skill.
- MCP: a tool source or not.
- Long-run turns: raise the step budget, or add `continue-as-new`.

## Consequences

- The service can be completed and tested without the sandbox.
- The computer capabilities have an owner: the sandbox platform, BUILD §6.3.
- EDA §8 and the code now agree: memory is files. Their intended placement on
  the VM is in [AGENT-COMPUTER.md](../AGENT-COMPUTER.md).
- "Learn by watching" has no owner until the sandbox exists and skill writing is
  decided.
