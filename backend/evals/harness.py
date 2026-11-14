"""Run a retriever over the question set and aggregate metrics per category and language pair."""

import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from app.modules.processing.arabic import search_normalize
from app.modules.processing.parsers import parse_text
from evals import metrics
from evals.corpus import CorpusDoc, Gold, Question

KS = (1, 3, 5, 10)


@dataclass(frozen=True)
class Retrieved:
    doc: str  # corpus slug
    chunk_index: int
    page_start: int
    page_end: int
    content_search: str  # search-normalized chunk text


Retriever = Callable[[Question], Awaitable[Sequence[Retrieved]]]


def judge(retrieved: Sequence[Retrieved], gold: Sequence[Gold]) -> list[int | None]:
    """For each retrieved chunk, the gold item it satisfies (credited once), else None."""
    needles = [search_normalize(g.evidence) for g in gold]
    credited: set[int] = set()
    out: list[int | None] = []
    for chunk in retrieved:
        match = next(
            (
                i
                for i, g in enumerate(gold)
                if i not in credited and chunk.doc == g.doc and needles[i] in chunk.content_search
            ),
            None,
        )
        if match is not None:
            credited.add(match)
        out.append(match)
    return out


def gold_pages(corpus: Sequence[CorpusDoc], gold: Gold) -> set[int]:
    """Pages of the (virtual) paginated document on which the evidence phrase lives."""
    doc = next(d for d in corpus if d.slug == gold.doc)
    needle = search_normalize(gold.evidence)
    return {p.number for p in parse_text(doc.text.encode()) if needle in search_normalize(p.text)}


def page_hit(
    retrieved: Sequence[Retrieved], gold: Sequence[Gold], corpus: Sequence[CorpusDoc], k: int
) -> float:
    wanted = {(g.doc, p) for g in gold for p in gold_pages(corpus, g)}
    for chunk in retrieved[:k]:
        if any(chunk.doc == d and chunk.page_start <= p <= chunk.page_end for d, p in wanted):
            return 1.0
    return 0.0


@dataclass
class Row:
    n: int = 0
    recall: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg10: float = 0.0
    page_hit5: float = 0.0


@dataclass
class Report:
    name: str
    overall: Row
    by_category: dict[str, Row]
    by_pair: dict[str, Row]
    digit_consistency: float | None  # share of digit-variant groups with identical rankings
    unanswerable: int
    failures: list[str]  # ids of answerable questions with no gold chunk in the top 10


def _aggregate(items: list[tuple[list[int | None], int, float]]) -> Row:
    row = Row(n=len(items))
    for k in KS:
        row.recall[k] = metrics.mean([metrics.recall_at_k(j, n, k) for j, n, _ in items])
    row.mrr = metrics.mean([metrics.reciprocal_rank(j, 10) for j, _, _ in items])
    row.ndcg10 = metrics.mean([metrics.ndcg_at_k(j, n, 10) for j, n, _ in items])
    row.page_hit5 = metrics.mean([p for _, _, p in items])
    return row


def _pair(question: Question, corpus_langs: dict[str, str]) -> str:
    docs = {corpus_langs[g.doc] for g in question.gold}
    return f"{question.lang}->{'/'.join(sorted(docs))}"


async def evaluate(
    name: str, retriever: Retriever, questions: Sequence[Question], corpus: Sequence[CorpusDoc]
) -> Report:
    langs = {d.slug: d.language for d in corpus}
    judged_by_cat: dict[str, list[tuple[list[int | None], int, float]]] = defaultdict(list)
    judged_by_pair: dict[str, list[tuple[list[int | None], int, float]]] = defaultdict(list)
    everything: list[tuple[list[int | None], int, float]] = []
    groups: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    failures: list[str] = []
    unanswerable = 0
    for question in questions:
        retrieved = list(await retriever(question))[:10]
        if question.group:
            groups[question.group].append(tuple(f"{r.doc}#{r.chunk_index}" for r in retrieved))
        if not question.gold:
            unanswerable += 1
            continue
        judged = judge(retrieved, question.gold)
        item = (judged, len(question.gold), page_hit(retrieved, question.gold, corpus, 5))
        everything.append(item)
        judged_by_cat[question.category].append(item)
        judged_by_pair[_pair(question, langs)].append(item)
        if not any(g is not None for g in judged):
            failures.append(question.id)
    consistency = (
        sum(1 for rankings in groups.values() if len(set(rankings)) == 1) / len(groups)
        if groups
        else None
    )
    return Report(
        name=name,
        overall=_aggregate(everything),
        by_category={c: _aggregate(v) for c, v in sorted(judged_by_cat.items())},
        by_pair={p: _aggregate(v) for p, v in sorted(judged_by_pair.items())},
        digit_consistency=consistency,
        unanswerable=unanswerable,
        failures=failures,
    )


def _fmt(row: Row) -> str:
    cells = [f"{row.recall[k]:.2f}" for k in KS]
    return (
        f"{row.n} | "
        + " | ".join(cells)
        + f" | {row.mrr:.2f} | {row.ndcg10:.2f} | {row.page_hit5:.2f}"
    )


def render_markdown(reports: Sequence[Report]) -> str:
    header = (
        "| n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    out: list[str] = []
    for report in reports:
        out.append(f"### {report.name}\n")
        out.append("| overall " + header.replace("| n |", "| n |", 1))
        out.append(f"| all | {_fmt(report.overall)} |\n")
        out.append("\n| category " + header)
        for category, row in report.by_category.items():
            out.append(f"| {category} | {_fmt(row)} |\n")
        out.append("\n| language pair " + header)
        for pair, row in report.by_pair.items():
            out.append(f"| {pair} | {_fmt(row)} |\n")
        if report.digit_consistency is not None:
            out.append(
                f"\nDigit-variant consistency (identical top-10 for Western / Arabic-Indic / "
                f"Persian digits): **{report.digit_consistency:.2f}**\n"
            )
        out.append(
            f"\nUnanswerable questions (not scored here): {report.unanswerable}. "
            f"Answerable questions with no relevant chunk in the top 10: "
            f"{', '.join(report.failures) or 'none'}.\n\n"
        )
    return "".join(out)


_TOKEN = re.compile(r"\w+", re.UNICODE)


def query_tokens(text: str) -> list[str]:
    """Normalized, tsquery-safe words of a question (the same normalization as the index)."""
    return _TOKEN.findall(search_normalize(text))


SUMMARY_COLUMNS = (
    ("overall R@5", None, 5),
    ("ar R@5", "ar_factoid", 5),
    ("en R@5", "en_factoid", 5),
    ("ar→en R@5", "cross_ar_to_en", 5),
    ("en→ar R@5", "cross_en_to_ar", 5),
    ("id R@5", "identifier", 5),
    ("para R@5", "paraphrase", 5),
    ("typo R@5", "typo_diacritic", 5),
    ("multi R@5", "multi_passage", 5),
)


def render_summary(reports: Sequence[Report]) -> str:
    """One row per configuration: the matrix a decision is made from."""
    head = "| configuration | MRR@10 | nDCG@10 | " + " | ".join(c[0] for c in SUMMARY_COLUMNS)
    head += " | digit consistency |\n|" + "---|" * (len(SUMMARY_COLUMNS) + 4) + "\n"
    rows = []
    for r in reports:
        cells = []
        for _, category, k in SUMMARY_COLUMNS:
            row = r.overall if category is None else r.by_category.get(category)
            cells.append("n/a" if row is None else f"{row.recall[k]:.2f}")
        digit = "n/a" if r.digit_consistency is None else f"{r.digit_consistency:.2f}"
        rows.append(
            f"| {r.name} | {r.overall.mrr:.2f} | {r.overall.ndcg10:.2f} | "
            + " | ".join(cells)
            + f" | {digit} |"
        )
    return head + "\n".join(rows) + "\n"


def check_gates(report: Report) -> list[tuple[str, bool, str]]:
    """The initial PLAN section 11.5 acceptance gates, evaluated for one configuration."""
    ar = report.by_category["ar_factoid"].recall[5]
    en = report.by_category["en_factoid"].recall[5]
    ar_en = report.by_category["cross_ar_to_en"].recall[5]
    en_ar = report.by_category["cross_en_to_ar"].recall[5]
    return [
        (
            "Arabic recall@5 within 10 points of English",
            en - ar <= 0.10,
            f"ar {ar:.2f} vs en {en:.2f}",
        ),
        ("Arabic→English recall@5 ≥ 0.80", ar_en >= 0.80, f"{ar_en:.2f}"),
        ("English→Arabic recall@5 ≥ 0.80", en_ar >= 0.80, f"{en_ar:.2f}"),
        (
            "digit variants identical",
            (report.digit_consistency or 0) == 1.0,
            f"{report.digit_consistency}",
        ),
    ]
