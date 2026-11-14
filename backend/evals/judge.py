"""LLM judge for FAITHFULNESS only (PLAN section 11.6), always a model different from the one that
wrote the answer, with a labelled calibration set so its agreement with the truth is REPORTED.

Deterministic checks (key facts, citations, numbers) come first elsewhere; the judge is a second,
fallible opinion about whether every claim in an answer is supported by the passages it cites.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.infrastructure.llm.base import ChatMessage, ChatModel
from evals import corpus

JUDGE_SYSTEM = """You check whether an ANSWER is fully supported by the numbered SOURCES.
A claim is supported only if a source states it (in any language). A number that is not in the
sources is unsupported. Do not use outside knowledge and do not judge whether the answer is useful.
Reply with ONLY a JSON object: {"supported": true or false, "unsupported_claims": ["..."]}."""

_JSON = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class JudgeItem:
    sources: tuple[str, ...]
    answer: str
    faithful: bool
    note: str


def parse_verdict(raw: str) -> bool | None:
    """True/False from the judge's JSON, None when it cannot be read (counted, never guessed)."""
    match = _JSON.search(raw)
    if not match:
        return None
    try:
        value = json.loads(match.group(0)).get("supported")
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, bool) else None


def judge_messages(answer: str, sources: Sequence[str]) -> list[ChatMessage]:
    blocks = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(sources, start=1))
    return [
        ChatMessage("system", JUDGE_SYSTEM),
        ChatMessage("user", f"SOURCES:\n{blocks}\n\nANSWER:\n{answer}"),
    ]


async def judge(
    model: ChatModel, answer: str, sources: Sequence[str], max_tokens: int = 200
) -> bool | None:
    raw = ""
    async for chunk in model.stream(judge_messages(answer, sources), max_tokens=max_tokens):
        raw += chunk.text
    return parse_verdict(raw)


def calibration_items(limit_each: int = 20) -> list[JudgeItem]:
    """Labelled by construction from the corpus: a faithful item states the gold evidence; an
    unfaithful one changes a figure or appends a claim the source never makes."""
    docs = {d.slug: d.text for d in corpus.build_corpus()}
    faithful: list[JudgeItem] = []
    broken: list[JudgeItem] = []
    for q in corpus.load_questions():
        if not q.gold or q.category in ("restricted", "multi_passage", "identifier"):
            continue
        gold = q.gold[0]
        source = docs[gold.doc]
        sentence = gold.evidence.rstrip(".")
        if len(faithful) < limit_each:
            faithful.append(JudgeItem((source,), f"{sentence} [1].", True, "states the evidence"))
        elif len(broken) < limit_each:
            if len(broken) % 2 == 0:
                changed = re.sub(r"\d+", lambda m: str(int(m.group(0)) + 7), sentence, count=1)
                if changed != sentence:
                    broken.append(
                        JudgeItem((source,), f"{changed} [1].", False, "changes a figure")
                    )
                    continue
            extra = (
                "Employees also receive a 20 percent annual bonus."
                if q.lang == "en"
                else "ويحصل الموظفون أيضاً على مكافأة سنوية بنسبة 20 في المائة."
            )
            broken.append(
                JudgeItem((source,), f"{sentence} [1]. {extra}", False, "adds an unsupported claim")
            )
        if len(faithful) >= limit_each and len(broken) >= limit_each:
            break
    return faithful + broken


def agreement(
    items: Sequence[JudgeItem], verdicts: Sequence[bool | None]
) -> dict[str, float | int]:
    """How often the judge is right on the labelled set (unreadable verdicts count as wrong)."""
    right = sum(1 for item, v in zip(items, verdicts, strict=True) if v is item.faithful)
    faithful = [v for item, v in zip(items, verdicts, strict=True) if item.faithful]
    unfaithful = [v for item, v in zip(items, verdicts, strict=True) if not item.faithful]
    return {
        "n": len(items),
        "accuracy": right / len(items) if items else 0.0,
        "faithful_recall": sum(1 for v in faithful if v is True) / len(faithful)
        if faithful
        else 0.0,
        "unfaithful_recall": sum(1 for v in unfaithful if v is False) / len(unfaithful)
        if unfaithful
        else 0.0,
        "unreadable": sum(1 for v in verdicts if v is None),
    }
