"""Add the LlamaIndex metadata fields from the metadata extraction guide."""

import json
import os
import time

from . import connect_drive

# Keys written by TitleExtractor, SummaryExtractor, KeywordExtractor, QuestionsAnsweredExtractor.
LLAMA_KEYS = (
    "document_title",
    "section_summary",
    "prev_section_summary",
    "excerpt_keywords",
    "questions_this_excerpt_can_answer",
)
MODEL = "google/gemma-4-31b-it:free"


def apply_fields(chunk, extracted):
    for key in LLAMA_KEYS:
        if extracted.get(key):
            chunk[key] = extracted[key]
    return chunk


def _self_check():
    chunk = apply_fields(
        {"text": "Hello"},
        {
            "document_title": "A hello",
            "section_summary": "Says hello.",
            "prev_section_summary": "Earlier page.",
            "excerpt_keywords": "hello",
            "questions_this_excerpt_can_answer": "What is said?",
            "document_date": "2024-11-21",
        },
    )
    assert chunk["excerpt_keywords"] == "hello"
    assert chunk["document_title"] == "A hello"
    assert "document_date" not in chunk


def finished(chunk, index):
    keys = ["document_title", "section_summary", "excerpt_keywords", "questions_this_excerpt_can_answer"]
    if index:
        keys.append("prev_section_summary")
    return all(chunk.get(key) for key in keys)


def llm():
    from llama_index.core.base.llms.types import LLMMetadata
    from llama_index.llms.openai import OpenAI

    class OpenRouter(OpenAI):
        # shortcut: LlamaIndex only knows OpenAI model names. Drop this when it accepts OpenRouter ids.
        @property
        def metadata(self) -> LLMMetadata:
            return LLMMetadata(
                context_window=131072,
                num_output=self.max_tokens or -1,
                is_chat_model=True,
                is_function_calling_model=False,
                model_name=self.model,
            )

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is missing.")
    return OpenRouter(
        model=MODEL,
        api_key=key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=2,
    )


def extractors(model):
    from llama_index.core.extractors import (
        KeywordExtractor,
        QuestionsAnsweredExtractor,
        SummaryExtractor,
        TitleExtractor,
    )

    return {
        "title": TitleExtractor(llm=model, nodes=5, num_workers=1),
        "summary": SummaryExtractor(llm=model, summaries=["self"], num_workers=1),
        "keywords": KeywordExtractor(llm=model, keywords=10, num_workers=1),
        "questions": QuestionsAnsweredExtractor(llm=model, questions=3, num_workers=1),
    }


def call_extractor(extractor, nodes):
    from openai import RateLimitError

    for attempt in range(6):
        try:
            return extractor.extract(nodes)
        except RateLimitError:
            if attempt == 5:
                raise
            time.sleep(30)


def save(path, chunks):
    path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))


def copy_prev(chunks):
    # SummaryExtractor sets this from the previous node's section_summary. Same copy, so a resume can do it.
    for index, chunk in enumerate(chunks):
        if index and chunks[index - 1].get("section_summary"):
            chunk["prev_section_summary"] = chunks[index - 1]["section_summary"]


def enrich_path(path, tools):
    from llama_index.core.schema import TextNode

    chunks = json.loads(path.read_text())
    nodes = [
        TextNode(
            text=f"{chunk.get('breadcrumb') or ''}\n\n{chunk.get('text') or ''}".strip(),
            ref_doc_id=path.name,
        )
        for chunk in chunks
    ]
    if any(not chunk.get("document_title") for chunk in chunks):
        try:
            rows = call_extractor(tools["title"], nodes)
        except Exception as exc:
            save(path, chunks)
            raise SystemExit(
                f"Stopped at {path.name} title: {type(exc).__name__}. Chunks already written can resume."
            ) from exc
        for chunk, row in zip(chunks, rows):
            apply_fields(chunk, row)
        save(path, chunks)
        print(f"{path.name} document_title", flush=True)

    for index, chunk in enumerate(chunks):
        copy_prev(chunks)
        if finished(chunk, index):
            continue
        pending = []
        if not chunk.get("section_summary"):
            pending.append(tools["summary"])
        if not chunk.get("excerpt_keywords"):
            pending.append(tools["keywords"])
        if not chunk.get("questions_this_excerpt_can_answer"):
            pending.append(tools["questions"])
        try:
            for extractor in pending:
                apply_fields(chunk, call_extractor(extractor, [nodes[index]])[0])
        except Exception as exc:
            copy_prev(chunks)
            save(path, chunks)
            raise SystemExit(
                f"Stopped at {path.name} chunk {index + 1}: {type(exc).__name__}. "
                "Chunks already written can resume."
            ) from exc
        copy_prev(chunks)
        save(path, chunks)
        print(f"{path.name} {index + 1}/{len(chunks)}", flush=True)
    copy_prev(chunks)
    save(path, chunks)


def main():
    paths = sorted(connect_drive.OUT.glob("*.chunks.json"))
    if not paths:
        raise SystemExit("No chunks in out/. Run chunk.py first.")
    tools = extractors(llm())
    for path in paths:
        enrich_path(path, tools)
        print(f"enriched {path}")


if __name__ == "__main__":
    _self_check()
    main()
