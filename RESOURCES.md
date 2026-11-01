# Always-on agents — resources

Curated sources for building a persistent, proactive agent. Knowledge sources ground the lessons; communities are where the judgement gets tested.

## Knowledge

- [Talk transcript: "How always-on agents work" (`ACHITECTURE.md`)](./ACHITECTURE.md)
  The course's primary source. Covers the four eras, the thin-client/thick-server harness, the `send_user` boundary, context engineering, sub-agents, durable workflows, and the training flywheel. Use for: the architecture this course builds and every claim about "how Grokbot does it".

- [Anthropic: "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents)
  The clearest statement that an agent is "an LLM using tools in a loop", plus the workflow-vs-agent distinction and tool-design advice. Use for: lesson 1, and whenever a design starts sprouting unnecessary framework.

- [Anthropic: "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  Context rot, compaction, structured note-taking, sub-agents, just-in-time retrieval. Use for: the context and memory lessons, and for justifying file-based memory.

- [Anthropic: "Writing tools for AI agents"](https://www.anthropic.com/engineering/writing-tools-for-agents)
  Tool ergonomics: naming, token-efficient returns, error messages, consolidating overlapping tools. Use for: designing `run_shell`, `send_user`, and the retrieval ladder.

- [12-Factor Agents (HumanLayer)](https://github.com/humanlayer/12-factor-agents)
  Production-minded principles from teams shipping agents: own your prompts, own your context window, unify execution and business state, own your control flow, compact errors, stateless reducer. Use for: lessons on durability, state, and the harness boundary. Start with [Factor 5](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-05-unify-execution-state.md) and [Factor 8](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-08-own-your-control-flow.md).

- [Temporal: durable execution](https://docs.temporal.io/encyclopedia/durable-execution)
  The precise definition of durable execution: replay from an event history, resume at the failed step. Use for: the durability lesson's vocabulary and its correctness claims. Python SDK: [docs.temporal.io/develop/python](https://docs.temporal.io/develop/python).

- [Firecracker microVMs](https://firecracker-microvm.github.io/)
  The isolation primitive behind "the agent has its own computer" — fast-booting VMs with snapshot/restore. Use for: the sandbox lesson.

- [Model Context Protocol — introduction](https://modelcontextprotocol.io/docs/getting-started/intro)
  The standard for connecting tools and data to models. Use for: plugins, dynamic tool discovery, and why tool schemas can eat a context window.

- [Pydantic AI docs](https://ai.pydantic.dev/)
  The Python agent framework this repo already chose. Agents, tools, and structured outputs. Use for: lessons 2+, once the raw loop is understood.

- [DeepSeek: context caching](https://api-docs.deepseek.com/guides/kv_cache)
  Prefix-unit caching, the `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` fields, and the best-effort caveat. Use for: lesson 05's measurement, and any claim about cache behaviour on this stack.

- [Hamel Husain: "Your AI Product Needs Evals"](https://hamel.dev/blog/posts/evals/)
  A practitioner's guide to building eval sets from real failures, with deterministic checks and assertions. Use for: lesson 10, and whenever the eval suite starts feeling like a vibe check.

- [OWASP LLM01: Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
  Why untrusted text is not an instruction, and why prompts are not a security boundary. Use for: lesson 09's threat model and any review of the input path.

- [Anthropic: prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
  How cache prefixes work and what invalidates them. Use for: the stable-prefix rule and the "cache miss is a bug" discussion.

- [Simon Willison: "How to think about agent frameworks"](https://simonwillison.net/2025/Sep/18/agents/)
  A short, durable definition of an agent and a useful scepticism about frameworks. Use for: calibrating what counts as an agent.

## Wisdom (Communities)

- [HumanLayer Discord](https://humanlayer.dev/discord)
  Practitioners building production agents around the 12-factor principles. Use for: durable-execution war stories, critique of a harness design.
- [Temporal community](https://temporal.io/community)
  Forums and Slack for workflow/durability questions. Use for: "my workflow replay does X" problems, which are notoriously subtle.
- [pydantic-ai issues](https://github.com/pydantic/pydantic-ai/issues)
  Maintainer-run, responsive. Use for: framework-specific bugs, not design advice.
- [Latent Space](https://www.latent.space/)
  Podcast/Discord with AI engineers shipping agents. Use for: staying current on harness and product patterns.

## Gaps
- No high-trust source yet on **proactive notification policy** ("when should the agent bug the user?"). The talk gives a heuristic, not a method. Look for HCI/notification research or production write-ups.
- No source yet on **browser control for agents** beyond vendor docs (accessibility tree vs screenshots vs pixels). Needed before the computer-use lesson.
- No verified **local (Nairobi) agent/AI meetup** listed yet. Add one when confirmed, not before.
