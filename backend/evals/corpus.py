"""The synthetic bilingual evaluation corpus.

Hand-written base documents (`corpus/*.md`, fictional company, no real data) plus deterministic
near-duplicate **variants** for fictional subsidiaries: same wording, different numbers. The
variants are hard negatives (a question about the 25-day policy must not be answered from the
21-day one), which is what makes recall@k meaningful on a corpus this small.

Everything is plain data: the same builder feeds the tests, the live ingestion and the metrics.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.modules.processing.arabic import search_normalize

HERE = Path(__file__).parent
CORPUS_DIR = HERE / "corpus"
QUESTIONS = HERE / "questions.jsonl"

CATEGORIES = (
    "en_factoid",
    "ar_factoid",
    "cross_ar_to_en",
    "cross_en_to_ar",
    "mixed",
    "digit_variant",
    "variant_entity",
    "restricted",
    "unanswerable",
)


@dataclass(frozen=True)
class CorpusDoc:
    slug: str
    language: str  # ar | en | mixed
    filename: str
    text: str
    restricted: bool = False

    @property
    def search_text(self) -> str:
        return search_normalize(self.text)


@dataclass(frozen=True)
class Gold:
    doc: str
    evidence: str  # a phrase that must appear in a relevant chunk (search-normalized match)


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    lang: str  # language of the question: ar | en
    category: str
    gold: tuple[Gold, ...]
    group: str | None = None  # digit-variant questions of one group must retrieve identically


# --- variants -----------------------------------------------------------------------------
# entity: (English name, Arabic name); literals are replaced simultaneously (longest first), so
# "25,000" and "5,000" cannot corrupt each other.
ENTITIES = {
    "cold_chain": ("Falcon Cold Chain", "شركة الصقر للتبريد"),
    "marine": ("Falcon Marine", "شركة الصقر البحرية"),
    "air_cargo": ("Falcon Air Cargo", "شركة الصقر للشحن الجوي"),
}
BASE_ENTITY = ("Falcon Logistics", "شركة الصقر للخدمات اللوجستية")

VARIANTS: dict[str, dict[str, dict[str, str]]] = {
    "hr_leave_en": {
        "cold_chain": {
            "25 working days": "21 working days",
            "30 working days": "26 working days",
            "maximum of 5 days": "maximum of 3 days",
            "31 March": "28 February",
            "15 days of sick leave": "10 days of sick leave",
            "70 days": "60 days",
            "longer than 2 consecutive days": "longer than 3 consecutive days",
        },
        "marine": {
            "25 working days": "28 working days",
            "30 working days": "32 working days",
            "maximum of 5 days": "maximum of 7 days",
            "31 March": "30 April",
            "15 days of sick leave": "20 days of sick leave",
            "70 days": "75 days",
            "longer than 2 consecutive days": "longer than 1 consecutive days",
        },
        "air_cargo": {
            "25 working days": "24 working days",
            "30 working days": "29 working days",
            "maximum of 5 days": "maximum of 4 days",
            "31 March": "31 January",
            "15 days of sick leave": "12 days of sick leave",
            "70 days": "65 days",
            "longer than 2 consecutive days": "longer than 5 consecutive days",
        },
    },
    "hr_leave_ar": {
        "cold_chain": {
            "25 يوم عمل": "21 يوم عمل",
            "ومدتها 10 أيام": "ومدتها 7 أيام",
            "مدتها 5 أيام عمل": "مدتها 3 أيام عمل",
            "30 يوماً في السنة": "20 يوماً في السنة",
            "يستحق الموظف 3 أيام إجازة": "يستحق الموظف 2 أيام إجازة",
        },
        "marine": {
            "25 يوم عمل": "28 يوم عمل",
            "ومدتها 10 أيام": "ومدتها 8 أيام",
            "مدتها 5 أيام عمل": "مدتها 7 أيام عمل",
            "30 يوماً في السنة": "45 يوماً في السنة",
            "يستحق الموظف 3 أيام إجازة": "يستحق الموظف 4 أيام إجازة",
        },
        "air_cargo": {
            "25 يوم عمل": "24 يوم عمل",
            "ومدتها 10 أيام": "ومدتها 12 يوماً",
            "مدتها 5 أيام عمل": "مدتها 4 أيام عمل",
            "30 يوماً في السنة": "25 يوماً في السنة",
            "يستحق الموظف 3 أيام إجازة": "يستحق الموظف 5 أيام إجازة",
        },
    },
    "travel_expense_en": {
        "cold_chain": {
            "SAR 300 per day": "SAR 250 per day",
            "SAR 450 per day": "SAR 400 per day",
            "6 hours": "5 hours",
            "SAR 800 per night": "SAR 700 per night",
            "SAR 1,200 per night": "SAR 1,000 per night",
            "SAR 75": "SAR 50",
            "10 working days": "7 working days",
        },
        "marine": {
            "SAR 300 per day": "SAR 350 per day",
            "SAR 450 per day": "SAR 500 per day",
            "6 hours": "7 hours",
            "SAR 800 per night": "SAR 900 per night",
            "SAR 1,200 per night": "SAR 1,400 per night",
            "SAR 75": "SAR 100",
            "10 working days": "14 working days",
        },
        "air_cargo": {
            "SAR 300 per day": "SAR 280 per day",
            "SAR 450 per day": "SAR 520 per day",
            "6 hours": "8 hours",
            "SAR 800 per night": "SAR 850 per night",
            "SAR 1,200 per night": "SAR 1,300 per night",
            "SAR 75": "SAR 60",
            "10 working days": "5 working days",
        },
    },
    "travel_expense_ar": {
        "cold_chain": {
            "25,000": "15,000",
            "5,000": "3,000",
            "0.90 ريال": "0.70 ريال",
            "مرتين في السنة": "مرة واحدة في السنة",
        },
        "marine": {
            "25,000": "40,000",
            "5,000": "8,000",
            "0.90 ريال": "1.10 ريال",
            "مرتين في السنة": "ثلاث مرات في السنة",
        },
        "air_cargo": {
            "25,000": "20,000",
            "5,000": "4,000",
            "0.90 ريال": "0.80 ريال",
            "مرتين في السنة": "أربع مرات في السنة",
        },
    },
    "it_security_en": {
        "cold_chain": {
            "14 characters": "16 characters",
            "within 24 hours": "within 12 hours",
            "within 1 hour": "within 2 hours",
            "2 working days": "3 working days",
        },
        "marine": {
            "14 characters": "10 characters",
            "within 24 hours": "within 48 hours",
            "within 1 hour": "within 4 hours",
            "2 working days": "5 working days",
        },
        "air_cargo": {
            "14 characters": "12 characters",
            "within 24 hours": "within 6 hours",
            "within 1 hour": "within 30 minutes",
            "2 working days": "1 working day",
        },
    },
    "it_security_ar": {
        "cold_chain": {
            "90 يوماً": "60 يوماً",
            "كل 6 أشهر": "كل 3 أشهر",
            "خلال ساعتين": "خلال 4 ساعات",
        },
        "marine": {"90 يوماً": "120 يوماً", "كل 6 أشهر": "كل 12 شهراً", "خلال ساعتين": "خلال 8 ساعات"},
        "air_cargo": {
            "90 يوماً": "180 يوماً",
            "كل 6 أشهر": "كل 4 أشهر",
            "خلال ساعتين": "خلال ساعة واحدة",
        },
    },
    "fleet_maintenance_en": {
        "cold_chain": {
            "10,000 km": "7,500 km",
            "every 6 months": "every 4 months",
            "3 mm": "4 mm",
            "9 hours": "8 hours",
            "45 minutes": "30 minutes",
            "4.5 hours": "4 hours",
            "110 km/h": "100 km/h",
        },
        "marine": {
            "10,000 km": "12,000 km",
            "every 6 months": "every 12 months",
            "3 mm": "2 mm",
            "9 hours": "10 hours",
            "45 minutes": "60 minutes",
            "4.5 hours": "5 hours",
            "110 km/h": "90 km/h",
        },
        "air_cargo": {
            "10,000 km": "8,000 km",
            "every 6 months": "every 5 months",
            "3 mm": "3.5 mm",
            "9 hours": "11 hours",
            "45 minutes": "40 minutes",
            "4.5 hours": "6 hours",
            "110 km/h": "120 km/h",
        },
    },
    "fleet_maintenance_ar": {
        "cold_chain": {
            "3 أطنان": "2 طن",
            "12 طناً": "10 أطنان",
            "50 متراً": "30 متراً",
            "8 سنوات": "6 سنوات",
            "400,000 كيلومتر": "300,000 كيلومتر",
        },
        "marine": {
            "3 أطنان": "4 أطنان",
            "12 طناً": "15 طناً",
            "50 متراً": "75 متراً",
            "8 سنوات": "10 سنوات",
            "400,000 كيلومتر": "500,000 كيلومتر",
        },
        "air_cargo": {
            "3 أطنان": "5 أطنان",
            "12 طناً": "20 طناً",
            "50 متراً": "100 متر",
            "8 سنوات": "7 سنوات",
            "400,000 كيلومتر": "350,000 كيلومتر",
        },
    },
}


def _substitute(text: str, mapping: dict[str, str]) -> str:
    pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def _language_of(slug: str) -> str:
    if slug.endswith("_ar"):
        return "ar"
    if slug.endswith("_en"):
        return "en"
    return "mixed"


def build_corpus() -> list[CorpusDoc]:
    docs: list[CorpusDoc] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        slug = path.stem
        text = path.read_text(encoding="utf-8")
        docs.append(
            CorpusDoc(slug, _language_of(slug), path.name, text, restricted="restricted" in slug)
        )
        for key, mapping in VARIANTS.get(slug, {}).items():
            en, ar = ENTITIES[key]
            lang = _language_of(slug)
            entity = ar if lang == "ar" else en
            base = BASE_ENTITY[1] if lang == "ar" else BASE_ENTITY[0]
            varied = _substitute(text, mapping).replace(base, entity)
            title_end = varied.index("\n")
            varied = f"{varied[:title_end]} ({entity}){varied[title_end:]}"
            docs.append(CorpusDoc(f"{slug}__{key}", lang, f"{slug}__{key}.md", varied))
    return docs


def load_questions(path: Path = QUESTIONS) -> list[Question]:
    questions: list[Question] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        questions.append(
            Question(
                id=raw["id"],
                text=raw["text"],
                lang=raw["lang"],
                category=raw["category"],
                gold=tuple(Gold(g["doc"], g["evidence"]) for g in raw["gold"]),
                group=raw.get("group"),
            )
        )
    return questions
