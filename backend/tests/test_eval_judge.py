"""The judge's plumbing: verdict parsing, the labelled calibration set, and agreement math."""

import pytest

from app.infrastructure.llm.base import ChatMessage
from evals import judge
from tests.fake_chat import FakeChat


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"supported": true, "unsupported_claims": []}', True),
        ('Sure! {"supported": false, "unsupported_claims": ["x"]} Hope that helps', False),
        ('```json\n{"supported": true}\n```', True),
        ('{"supported": "yes"}', None),  # not a boolean: never guessed
        ("I think it is supported", None),
        ("{not json}", None),
        ("", None),
    ],
)
def test_the_verdict_is_read_strictly(raw: str, expected: bool | None) -> None:
    assert judge.parse_verdict(raw) is expected


async def test_the_judge_asks_with_numbered_sources_and_the_answer() -> None:
    chat = FakeChat('{"supported": true, "unsupported_claims": []}')
    assert await judge.judge(chat, "25 days [1].", ["Employees get 25 days."]) is True
    system, user = chat.calls[0]
    assert "ONLY a JSON object" in system.content and "[1] Employees get 25 days." in user.content
    assert user.content.endswith("ANSWER:\n25 days [1].")
    assert isinstance(system, ChatMessage)


def test_the_calibration_set_is_balanced_labelled_and_bilingual() -> None:
    items = judge.calibration_items()
    assert len(items) == 40
    assert sum(i.faithful for i in items) == 20 and sum(not i.faithful for i in items) == 20
    notes = {i.note for i in items if not i.faithful}
    assert notes == {"changes a figure", "adds an unsupported claim"}
    for item in items:
        assert (item.sources and item.answer.endswith(("[1].", "%."))) or "[1]" in item.answer
    arabic = [i for i in items if any("؀" <= c <= "ۿ" for c in i.answer)]
    assert 8 <= len(arabic) <= 36  # both languages are represented


def test_every_unfaithful_item_really_differs_from_the_source() -> None:
    for item in judge.calibration_items():
        if item.note == "changes a figure":
            assert item.answer.split(" [1]")[0] not in item.sources[0]
        if item.note == "adds an unsupported claim":
            assert ("20 percent" in item.answer) or ("20 في المائة" in item.answer)
            assert ("20 percent" not in item.sources[0]) and ("20 في المائة" not in item.sources[0])


def test_agreement_counts_unreadable_verdicts_as_wrong() -> None:
    items = judge.calibration_items()[:4]
    labels = [i.faithful for i in items]
    perfect = judge.agreement(items, labels)
    assert perfect["accuracy"] == 1.0 and perfect["unreadable"] == 0
    flawed = judge.agreement(items, [None, *labels[1:]])
    assert flawed["accuracy"] == pytest.approx(0.75) and flawed["unreadable"] == 1
