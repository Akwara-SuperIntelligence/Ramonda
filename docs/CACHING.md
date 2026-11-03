# Caching: what the providers do, and what this service does

Scope: prompt caching for the agent service. It records what we measured, what
the providers document, and the rules the harness must keep. Design context is
in [EDA.md](EDA.md); the lesson is
[05 — Stay lean](../course/lessons/0005-stay-lean.html).

## 1. The rule

A cache is a **prefix match**. The provider stores a prefix and reuses it only
when a later request begins with exactly the same tokens. Stable content goes
first; new content goes last. One changed token near the start invalidates every
token after it.

## 2. The talk's slides, mapped to lesson 05

| Slide | Lesson 05 section | Our status |
|---|---|---|
| Keep the start of the prompt the same | **2. Measure the cache** (the stable-prefix diagram) and **3. The other levers → Order, hashing, and pre-warming** | System prompt is constant within a run and history is appended. Not yet pinned across deploys. |
| Keep the main context small | **3. The other levers → Tool search, Files over context, Compaction** | All three built: names-only tools, output over 2,000 characters to a file, summary after a threshold. |
| Treat a cache miss like a bug | **2. Measure the cache** and **3. The other levers → Order, hashing, and pre-warming** | Measured per call. Fixed order. One hash for the whole prompt, not per section. No pre-warm. |
| Summarize while you're away | **3. The other levers → Compaction** | Compaction runs at the start of a turn, which is while the previous prefix is still warm. It does not run after a big turn while idle. |

## 3. Are we keeping the start the same?

**Within a conversation, yes.** The system message is built once from `RULES` and
`TOOLS`. History is read from Postgres in order and appended at the end. Nothing
in the prompt carries a timestamp, request id, or random value.

**Across a deploy: now yes.** Each conversation stores a `prompt_version` on its
first turn. `PROMPTS` keeps every version, so a deploy adds a version instead of
replacing one, and a running conversation keeps the text it started with. The
version and three section hashes are recorded with every model call.

## 4. What we measured on DeepSeek

Method: a novel prefix per size, two identical requests, twelve seconds apart.

| Prompt tokens | Cache hit on the second call |
|---|---|
| 153 | 0 |
| 208 | 0 |
| 271 | 128 |
| 310 | 128 |
| 431 | 256 |
| 830 | 640 |
| 1820 | 1664 |

Findings:

- There is a **minimum size**, between 208 and 271 tokens. Below it, identical
  requests do not hit at all.
- Above it, hits come in blocks and the tail of the prompt is not cached.
- The lesson's meter used an 18,600-character prefix, about **3,613 tokens**, and
  reported 3,456 cached. Short prefixes were never part of that measurement.

So a zero hit ratio on a short conversation is expected, not a defect. The talk's
"a cache miss is a bug" applies once the prompt is above the provider's minimum.

## 5. Provider windows

| Provider | Activation | Minimum cacheable | Lifetime | Read cost | Write cost |
|---|---|---|---|---|---|
| **DeepSeek** | Automatic | Not documented; measured between 208 and 271 tokens | Hours to days, best effort | Below miss price; check the pricing page | None stated |
| **Anthropic** | `cache_control`, or automatic | Varies by model, roughly 512 to 4,096 tokens | 5 minutes by default, 1 hour optional | 0.1x input, lower on newest models | 1.25x (5m), 2x (1h) |
| **OpenAI** | Automatic | 1,024 visible tokens on GPT-5.6 and later; varies earlier | 30 minutes default, 12 hours optional on GPT-5.6+; earlier roughly 5 to 10 minutes, up to 1 hour | 0.1x input | 1.25x (30m), 2.5x (12h) |
| **Google Gemini** | Implicit and explicit | Varies by model; not verified here | Configurable on explicit caches | Discounted; check the pricing page | Charged per storage time |

Gemini's documentation redirects to a JavaScript application and could not be
read in this environment, so its row is marked unverified rather than guessed.

## 6. What the harness now does

1. **Pins the prompt per conversation.** `prompt_version` is stored on the first
   turn and every model call uses that version. A deploy adds a version; it does
   not replace one.
2. **Hashes each section separately.** `hash_rules`, `hash_tools`, and
   `hash_memory` are recorded with every call, so a change names the section that
   moved.
3. **Pre-warms on typing.** A client publishes `agent.command.typing` with a
   `conversation_id`; the consumer sends the pinned system prompt with a one-token
   request. No turn, no message rows.
4. **Compaction is a deliberate prefix reset.** After a summary the start changes
   once. Expect one miss.
5. **Does not chase hits below the minimum.** Below roughly 250 tokens on
   DeepSeek there is nothing to hit.

## 7. Sources

- DeepSeek, [Context Caching](https://api-docs.deepseek.com/guides/kv_cache).
- Anthropic, [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
- OpenAI, [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
- Lesson [05 — Stay lean](../course/lessons/0005-stay-lean.html), including
  `course/build/lesson-05/meter.py`.
- The talk, [ACHITECTURE.md](ACHITECTURE.md) §05.
