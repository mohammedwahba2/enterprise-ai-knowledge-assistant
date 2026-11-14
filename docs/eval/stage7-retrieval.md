# Stage 7 retrieval evaluation and ablations

Generated 2026-11-14 by `EVAL_LIVE_OLLAMA=1 pytest tests/test_eval_stage7.py`.

- Corpus: 44 synthetic documents (24 near-duplicate variants used as hard negatives), each one chunk.
- Questions: 151 (141 answerable).
- Candidates evaluated: multilingual-e5-large, Arabic-Triplet-Matryoshka-V2.
- Reranker: not evaluated (not downloaded).

## Summary matrix (recall@5 unless stated)

| configuration | MRR@10 | nDCG@10 | overall R@5 | ar R@5 | en R@5 | ar→en R@5 | en→ar R@5 | id R@5 | para R@5 | typo R@5 | multi R@5 | digit consistency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FUSION GRID k=60 vector-weight=1 | 0.71 | 0.73 | 0.77 | 1.00 | 0.93 | 0.00 | 0.12 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=60 vector-weight=2 | 0.68 | 0.71 | 0.74 | 0.93 | 0.97 | 0.00 | 0.12 | 0.92 | 0.83 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=60 vector-weight=3 | 0.68 | 0.71 | 0.75 | 0.93 | 0.97 | 0.06 | 0.19 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=60 vector-weight=4 | 0.69 | 0.74 | 0.76 | 0.93 | 0.97 | 0.12 | 0.25 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=20 vector-weight=1 | 0.71 | 0.73 | 0.77 | 1.00 | 0.97 | 0.00 | 0.12 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=20 vector-weight=2 | 0.71 | 0.77 | 0.78 | 0.93 | 0.93 | 0.19 | 0.31 | 0.92 | 0.83 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=20 vector-weight=3 | 0.71 | 0.77 | 0.83 | 0.93 | 0.97 | 0.56 | 0.44 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=20 vector-weight=4 | 0.74 | 0.79 | 0.88 | 0.93 | 0.97 | 0.69 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=10 vector-weight=1 | 0.73 | 0.78 | 0.79 | 1.00 | 0.97 | 0.12 | 0.19 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=10 vector-weight=2 | 0.74 | 0.79 | 0.87 | 0.93 | 0.93 | 0.69 | 0.62 | 0.92 | 0.83 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=10 vector-weight=3 | 0.77 | 0.82 | 0.90 | 0.93 | 0.93 | 0.88 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=10 vector-weight=4 | 0.78 | 0.83 | 0.91 | 0.93 | 0.97 | 0.94 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=5 vector-weight=1 | 0.75 | 0.81 | 0.86 | 1.00 | 0.97 | 0.44 | 0.44 | 1.00 | 0.83 | 1.00 | 1.00 | 1.00 |
| FUSION GRID k=5 vector-weight=2 | 0.78 | 0.83 | 0.91 | 0.93 | 0.93 | 0.94 | 0.75 | 0.92 | 0.83 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=5 vector-weight=3 | 0.81 | 0.85 | 0.90 | 0.93 | 0.93 | 0.94 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=5 vector-weight=4 | 0.81 | 0.85 | 0.91 | 0.93 | 0.93 | 1.00 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=3 vector-weight=1 | 0.77 | 0.82 | 0.91 | 1.00 | 1.00 | 0.62 | 0.69 | 1.00 | 0.83 | 1.00 | 1.00 | 1.00 |
| FUSION GRID k=3 vector-weight=2 | 0.82 | 0.86 | 0.94 | 0.96 | 0.97 | 0.94 | 0.75 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 |
| FUSION GRID k=3 vector-weight=3 | 0.82 | 0.86 | 0.91 | 0.93 | 0.93 | 1.00 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| FUSION GRID k=3 vector-weight=4 | 0.81 | 0.85 | 0.91 | 0.93 | 0.93 | 1.00 | 0.75 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| full text, language-aware (arabic/english configs) | 0.71 | 0.73 | 0.75 | 1.00 | 0.97 | 0.00 | 0.00 | 1.00 | 1.00 | 0.88 | 0.62 | 1.00 |
| full text, simple config | 0.61 | 0.64 | 0.70 | 0.96 | 0.90 | 0.00 | 0.00 | 1.00 | 1.00 | 0.88 | 0.88 | 1.00 |
| full text, raw (no normalization at all) | 0.60 | 0.63 | 0.68 | 0.96 | 0.90 | 0.00 | 0.00 | 1.00 | 1.00 | 0.62 | 0.88 | 0.00 |
| vector, bge-m3 | 0.80 | 0.84 | 0.90 | 0.89 | 0.90 | 1.00 | 0.81 | 0.92 | 0.67 | 0.88 | 0.88 | 1.00 |
| vector, bge-m3, query digits NOT folded | 0.80 | 0.84 | 0.90 | 0.89 | 0.90 | 1.00 | 0.81 | 0.92 | 0.67 | 0.88 | 0.88 | 0.00 |
| hybrid RRF, bge-m3 + full text (language-aware) | 0.71 | 0.73 | 0.77 | 1.00 | 0.93 | 0.00 | 0.12 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| hybrid RRF, bge-m3 + full text (simple) | 0.81 | 0.85 | 0.94 | 0.93 | 1.00 | 0.94 | 0.75 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| hybrid RRF, bge-m3 + full text (raw) | 0.81 | 0.85 | 0.94 | 0.93 | 1.00 | 0.94 | 0.75 | 1.00 | 1.00 | 0.75 | 1.00 | 0.25 |
| hybrid RRF, bge-m3 + full text (language-aware), chosen k/weight | 0.82 | 0.86 | 0.94 | 0.96 | 0.97 | 0.94 | 0.75 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 |
| vector, multilingual-e5-large | 0.78 | 0.82 | 0.87 | 0.96 | 1.00 | 0.31 | 0.62 | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 |
| hybrid RRF, multilingual-e5-large + full text (language-aware) | 0.78 | 0.81 | 0.86 | 1.00 | 1.00 | 0.12 | 0.62 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| vector, Arabic-Triplet-Matryoshka-V2 | 0.48 | 0.54 | 0.60 | 0.89 | 0.72 | 0.06 | 0.00 | 0.50 | 0.67 | 0.62 | 0.62 | 1.00 |
| hybrid RRF, Arabic-Triplet-Matryoshka-V2 + full text (language-aware) | 0.56 | 0.61 | 0.74 | 0.96 | 0.97 | 0.00 | 0.00 | 1.00 | 0.83 | 0.88 | 0.75 | 1.00 |
| hybrid RRF, all embedders + full text (ensemble) | 0.80 | 0.84 | 0.92 | 0.96 | 1.00 | 0.81 | 0.69 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 |
| language-routed: Arabic questions use the ensemble, English the primary hybrid | 0.80 | 0.84 | 0.92 | 0.96 | 0.97 | 0.81 | 0.75 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 |
| PRODUCT: POST /search (pgvector HNSW + full text, RRF, permission-filtered) | 0.81 | 0.85 | 0.94 | 0.96 | 0.97 | 0.94 | 0.75 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 |

## Gates (initial, PLAN section 11.5) for the product path

- PASS: Arabic recall@5 within 10 points of English (ar 0.96 vs en 0.97)
- PASS: Arabic→English recall@5 ≥ 0.80 (0.94)
- FAIL: English→Arabic recall@5 ≥ 0.80 (0.75)
- PASS: digit variants identical (1.0)

## Fusion cell chosen on the stage 6 questions (dev), checked on the new ones (test)

| fusion cell | dev R@5 (n=69) | test R@5 (n=82) | dev MRR | test MRR |
|---|---|---|---|---|
| k=60 weight=1 | 0.76 | 0.77 | 0.72 | 0.70 |
| k=60 weight=2 | 0.75 | 0.74 | 0.69 | 0.68 |
| k=60 weight=3 | 0.76 | 0.74 | 0.69 | 0.67 |
| k=60 weight=4 | 0.78 | 0.75 | 0.70 | 0.68 |
| k=20 weight=1 | 0.76 | 0.78 | 0.72 | 0.71 |
| k=20 weight=2 | 0.78 | 0.78 | 0.72 | 0.71 |
| k=20 weight=3 | 0.84 | 0.83 | 0.72 | 0.71 |
| k=20 weight=4 | 0.89 | 0.88 | 0.75 | 0.73 |
| k=10 weight=1 | 0.79 | 0.79 | 0.74 | 0.73 |
| k=10 weight=2 | 0.87 | 0.87 | 0.75 | 0.73 |
| k=10 weight=3 | 0.92 | 0.88 | 0.77 | 0.76 |
| k=10 weight=4 | 0.92 | 0.90 | 0.80 | 0.77 |
| k=5 weight=1 | 0.84 | 0.87 | 0.76 | 0.75 |
| k=5 weight=2 | 0.92 | 0.91 | 0.78 | 0.78 |
| k=5 weight=3 | 0.92 | 0.89 | 0.81 | 0.80 |
| k=5 weight=4 | 0.94 | 0.89 | 0.79 | 0.82 |
| k=3 weight=1 | 0.89 | 0.94 | 0.76 | 0.77 |
| k=3 weight=2 | 0.92 | 0.95 | 0.81 | 0.82 |
| k=3 weight=3 | 0.94 | 0.89 | 0.80 | 0.83 |
| k=3 weight=4 | 0.94 | 0.89 | 0.79 | 0.82 |

## Detail per configuration

### FUSION GRID k=60 vector-weight=1
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.65 | 0.72 | 0.77 | 0.79 | 0.71 | 0.73 | 0.77 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 0.93 | 1.00 | 1.00 | 0.91 | 0.93 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.90 | 0.93 | 1.00 | 0.88 | 0.91 | 0.93 |
| identifier | 12 | 0.83 | 0.92 | 1.00 | 1.00 | 0.89 | 0.92 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 0.88 | 1.00 | 1.00 | 1.00 | 0.94 | 1.00 |
| paraphrase | 6 | 0.67 | 0.83 | 1.00 | 1.00 | 0.78 | 0.84 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 0.88 | 0.88 | 0.88 | 0.81 | 0.83 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.85 | 0.95 | 0.98 | 0.98 | 0.92 | 0.93 | 0.98 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| en->en | 50 | 0.82 | 0.89 | 0.96 | 1.00 | 0.89 | 0.91 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, typo-06.

### FUSION GRID k=60 vector-weight=2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.62 | 0.72 | 0.74 | 0.79 | 0.68 | 0.71 | 0.74 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.97 | 1.00 | 0.84 | 0.88 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.75 | 0.88 | 1.00 | 0.88 | 0.87 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.73 | 0.79 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 0.88 | 0.73 | 0.77 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.81 | 0.92 | 0.94 | 0.98 | 0.87 | 0.90 | 0.95 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| en->en | 50 | 0.78 | 0.91 | 0.94 | 1.00 | 0.87 | 0.90 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, typo-06.

### FUSION GRID k=60 vector-weight=3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.61 | 0.71 | 0.75 | 0.84 | 0.68 | 0.71 | 0.75 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.89 | 0.93 | 0.96 | 0.85 | 0.88 | 0.93 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.06 | 0.31 | 0.04 | 0.10 | 0.06 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.19 | 0.38 | 0.07 | 0.14 | 0.19 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.97 | 1.00 | 0.82 | 0.87 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.94 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.72 | 0.78 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.90 | 0.92 | 0.96 | 0.86 | 0.89 | 0.93 |
| ar->en | 16 | 0.00 | 0.00 | 0.06 | 0.31 | 0.04 | 0.10 | 0.06 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.19 | 0.38 | 0.07 | 0.14 | 0.19 |
| en->en | 50 | 0.76 | 0.90 | 0.94 | 1.00 | 0.85 | 0.89 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-06, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, ar-18, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-14, x-ar-en-15, x-en-ar-11, x-en-ar-12, x-en-ar-14, x-en-ar-15, typo-06.

### FUSION GRID k=60 vector-weight=4
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.61 | 0.71 | 0.76 | 0.93 | 0.69 | 0.74 | 0.77 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.89 | 0.93 | 0.96 | 0.85 | 0.87 | 0.93 |
| cross_ar_to_en | 16 | 0.00 | 0.06 | 0.12 | 0.88 | 0.12 | 0.28 | 0.12 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.25 | 0.69 | 0.11 | 0.24 | 0.25 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.97 | 0.97 | 0.81 | 0.85 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.94 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.71 | 0.77 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.88 | 0.92 | 0.96 | 0.86 | 0.88 | 0.93 |
| ar->en | 16 | 0.00 | 0.06 | 0.12 | 0.88 | 0.12 | 0.28 | 0.12 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.25 | 0.69 | 0.11 | 0.24 | 0.25 |
| en->en | 50 | 0.76 | 0.90 | 0.94 | 0.98 | 0.84 | 0.88 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, en-28, ar-18, x-ar-en-09, x-en-ar-11, x-en-ar-14, typo-06.

### FUSION GRID k=20 vector-weight=1
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.72 | 0.77 | 0.79 | 0.71 | 0.73 | 0.77 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 0.93 | 1.00 | 1.00 | 0.90 | 0.93 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.90 | 0.97 | 1.00 | 0.88 | 0.91 | 0.97 |
| identifier | 12 | 0.83 | 0.92 | 1.00 | 1.00 | 0.90 | 0.92 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 0.88 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 1.00 | 1.00 | 0.87 | 0.90 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 0.88 | 0.88 | 0.88 | 0.81 | 0.83 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 0.95 | 0.98 | 0.98 | 0.93 | 0.94 | 0.98 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| en->en | 50 | 0.82 | 0.89 | 0.98 | 1.00 | 0.89 | 0.91 | 0.98 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, typo-06.

### FUSION GRID k=20 vector-weight=2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.62 | 0.73 | 0.78 | 0.97 | 0.71 | 0.77 | 0.78 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| cross_ar_to_en | 16 | 0.00 | 0.06 | 0.19 | 1.00 | 0.16 | 0.35 | 0.19 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.31 | 0.81 | 0.14 | 0.29 | 0.31 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.72 | 0.79 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 0.88 | 0.73 | 0.77 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.81 | 0.92 | 0.95 | 0.98 | 0.87 | 0.90 | 0.95 |
| ar->en | 16 | 0.00 | 0.06 | 0.19 | 1.00 | 0.16 | 0.35 | 0.19 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.31 | 0.81 | 0.14 | 0.29 | 0.31 |
| en->en | 50 | 0.78 | 0.92 | 0.92 | 1.00 | 0.87 | 0.90 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-05, x-en-ar-07, x-en-ar-14, typo-06.

### FUSION GRID k=20 vector-weight=3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.61 | 0.77 | 0.83 | 0.95 | 0.71 | 0.77 | 0.84 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.89 | 0.93 | 0.93 | 0.84 | 0.86 | 0.93 |
| cross_ar_to_en | 16 | 0.00 | 0.25 | 0.56 | 1.00 | 0.21 | 0.40 | 0.56 |
| cross_en_to_ar | 16 | 0.00 | 0.38 | 0.44 | 0.81 | 0.23 | 0.37 | 0.44 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.97 | 1.00 | 0.82 | 0.87 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 0.69 | 0.73 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.90 | 0.92 | 0.93 | 0.86 | 0.87 | 0.93 |
| ar->en | 16 | 0.00 | 0.25 | 0.56 | 1.00 | 0.21 | 0.40 | 0.56 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.38 | 0.44 | 0.81 | 0.23 | 0.37 | 0.44 |
| en->en | 50 | 0.76 | 0.90 | 0.94 | 1.00 | 0.85 | 0.89 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-05, x-en-ar-07, ar-18, x-en-ar-14, para-04, typo-06.

### FUSION GRID k=20 vector-weight=4
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.63 | 0.78 | 0.88 | 0.95 | 0.74 | 0.79 | 0.89 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.89 | 0.93 | 0.93 | 0.84 | 0.86 | 0.93 |
| cross_ar_to_en | 16 | 0.12 | 0.38 | 0.69 | 1.00 | 0.35 | 0.50 | 0.69 |
| cross_en_to_ar | 16 | 0.06 | 0.38 | 0.75 | 0.88 | 0.32 | 0.46 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.97 | 0.97 | 0.81 | 0.85 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.94 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 0.69 | 0.73 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.88 | 0.92 | 0.93 | 0.85 | 0.87 | 0.93 |
| ar->en | 16 | 0.12 | 0.38 | 0.69 | 1.00 | 0.35 | 0.50 | 0.69 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.06 | 0.38 | 0.75 | 0.88 | 0.32 | 0.46 | 0.75 |
| en->en | 50 | 0.76 | 0.90 | 0.94 | 0.98 | 0.84 | 0.88 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-05, en-28, ar-18, x-en-ar-14, para-04, typo-06.

### FUSION GRID k=10 vector-weight=1
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.74 | 0.79 | 0.93 | 0.73 | 0.78 | 0.79 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 0.96 | 1.00 | 1.00 | 0.91 | 0.93 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.12 | 0.75 | 0.10 | 0.25 | 0.12 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.19 | 0.62 | 0.10 | 0.21 | 0.19 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.93 | 0.97 | 1.00 | 0.89 | 0.91 | 0.97 |
| identifier | 12 | 0.83 | 0.92 | 1.00 | 1.00 | 0.90 | 0.92 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.96 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 1.00 | 1.00 | 0.87 | 0.90 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 0.88 | 0.88 | 1.00 | 0.82 | 0.86 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 0.96 | 0.98 | 1.00 | 0.93 | 0.95 | 0.98 |
| ar->en | 16 | 0.00 | 0.00 | 0.12 | 0.75 | 0.10 | 0.25 | 0.12 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.19 | 0.62 | 0.10 | 0.21 | 0.19 |
| en->en | 50 | 0.82 | 0.92 | 0.98 | 1.00 | 0.89 | 0.92 | 0.98 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-02, x-ar-en-04, x-en-ar-02, x-en-ar-05, x-en-ar-07, x-ar-en-09, x-ar-en-15, x-en-ar-09, x-en-ar-12, x-en-ar-14.

### FUSION GRID k=10 vector-weight=2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.63 | 0.79 | 0.87 | 0.97 | 0.74 | 0.79 | 0.87 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| cross_ar_to_en | 16 | 0.06 | 0.31 | 0.69 | 1.00 | 0.27 | 0.44 | 0.69 |
| cross_en_to_ar | 16 | 0.00 | 0.38 | 0.62 | 0.81 | 0.26 | 0.39 | 0.62 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.72 | 0.79 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 0.88 | 0.73 | 0.77 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.81 | 0.92 | 0.95 | 0.98 | 0.87 | 0.90 | 0.95 |
| ar->en | 16 | 0.06 | 0.31 | 0.69 | 1.00 | 0.27 | 0.44 | 0.69 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.38 | 0.62 | 0.81 | 0.26 | 0.39 | 0.62 |
| en->en | 50 | 0.78 | 0.92 | 0.92 | 1.00 | 0.87 | 0.90 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-05, x-en-ar-07, x-en-ar-14, typo-06.

### FUSION GRID k=10 vector-weight=3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.65 | 0.84 | 0.90 | 0.97 | 0.77 | 0.82 | 0.90 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.89 | 0.93 | 0.93 | 0.82 | 0.85 | 0.93 |
| cross_ar_to_en | 16 | 0.31 | 0.56 | 0.88 | 1.00 | 0.51 | 0.63 | 0.88 |
| cross_en_to_ar | 16 | 0.12 | 0.69 | 0.75 | 0.94 | 0.42 | 0.55 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.93 | 1.00 | 0.82 | 0.87 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.71 | 0.77 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.77 | 0.90 | 0.92 | 0.95 | 0.85 | 0.87 | 0.93 |
| ar->en | 16 | 0.31 | 0.56 | 0.88 | 1.00 | 0.51 | 0.63 | 0.88 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.12 | 0.69 | 0.75 | 0.94 | 0.42 | 0.55 | 0.75 |
| en->en | 50 | 0.76 | 0.90 | 0.92 | 1.00 | 0.85 | 0.89 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, ar-18, x-en-ar-14, typo-06.

### FUSION GRID k=10 vector-weight=4
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.68 | 0.85 | 0.91 | 0.96 | 0.78 | 0.83 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.89 | 0.93 | 0.93 | 0.82 | 0.85 | 0.93 |
| cross_ar_to_en | 16 | 0.38 | 0.75 | 0.94 | 1.00 | 0.59 | 0.69 | 0.94 |
| cross_en_to_ar | 16 | 0.31 | 0.69 | 0.75 | 0.94 | 0.53 | 0.63 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.97 | 1.00 | 0.82 | 0.86 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.94 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 0.69 | 0.73 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.77 | 0.88 | 0.92 | 0.93 | 0.84 | 0.86 | 0.93 |
| ar->en | 16 | 0.38 | 0.75 | 0.94 | 1.00 | 0.59 | 0.69 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.31 | 0.69 | 0.75 | 0.94 | 0.53 | 0.63 | 0.75 |
| en->en | 50 | 0.76 | 0.90 | 0.94 | 1.00 | 0.85 | 0.88 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, ar-18, x-en-ar-14, para-04, typo-06.

### FUSION GRID k=5 vector-weight=1
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.79 | 0.86 | 0.97 | 0.75 | 0.81 | 0.86 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 1.00 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.19 | 0.44 | 0.94 | 0.20 | 0.37 | 0.44 |
| cross_en_to_ar | 16 | 0.00 | 0.12 | 0.44 | 0.81 | 0.17 | 0.31 | 0.44 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.93 | 0.97 | 1.00 | 0.89 | 0.92 | 0.97 |
| identifier | 12 | 0.83 | 1.00 | 1.00 | 1.00 | 0.90 | 0.93 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.86 | 0.89 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 1.00 | 1.00 | 1.00 | 0.85 | 0.89 | 1.00 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 1.00 | 1.00 | 1.00 | 0.94 | 0.96 | 1.00 |
| ar->en | 16 | 0.00 | 0.19 | 0.44 | 0.94 | 0.20 | 0.37 | 0.44 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.12 | 0.44 | 0.81 | 0.17 | 0.31 | 0.44 |
| en->en | 50 | 0.82 | 0.94 | 0.96 | 1.00 | 0.90 | 0.92 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-05, x-en-ar-07, x-ar-en-15, x-en-ar-14.

### FUSION GRID k=5 vector-weight=2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.85 | 0.91 | 0.98 | 0.78 | 0.83 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.93 | 1.00 | 0.84 | 0.88 | 0.93 |
| cross_ar_to_en | 16 | 0.31 | 0.56 | 0.94 | 1.00 | 0.53 | 0.64 | 0.94 |
| cross_en_to_ar | 16 | 0.12 | 0.69 | 0.75 | 0.88 | 0.41 | 0.53 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.93 | 1.00 | 0.85 | 0.89 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.74 | 0.80 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 0.88 | 0.73 | 0.77 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.92 | 0.95 | 0.98 | 0.87 | 0.90 | 0.95 |
| ar->en | 16 | 0.31 | 0.56 | 0.94 | 1.00 | 0.53 | 0.64 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.12 | 0.69 | 0.75 | 0.88 | 0.41 | 0.53 | 0.75 |
| en->en | 50 | 0.78 | 0.92 | 0.92 | 1.00 | 0.87 | 0.90 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-05, x-en-ar-14, typo-06.

### FUSION GRID k=5 vector-weight=3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.88 | 0.90 | 0.98 | 0.81 | 0.85 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.93 | 0.96 | 0.82 | 0.86 | 0.93 |
| cross_ar_to_en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.68 | 0.76 | 0.94 |
| cross_en_to_ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.93 | 1.00 | 0.82 | 0.87 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.71 | 0.77 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.77 | 0.92 | 0.92 | 0.96 | 0.85 | 0.88 | 0.93 |
| ar->en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.68 | 0.76 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| en->en | 50 | 0.76 | 0.90 | 0.92 | 1.00 | 0.85 | 0.89 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-14, typo-06.

### FUSION GRID k=5 vector-weight=4
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.86 | 0.91 | 0.97 | 0.81 | 0.85 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.70 | 0.85 | 0.93 | 0.93 | 0.80 | 0.83 | 0.93 |
| cross_ar_to_en | 16 | 0.56 | 0.88 | 1.00 | 1.00 | 0.73 | 0.79 | 1.00 |
| cross_en_to_ar | 16 | 0.56 | 0.69 | 0.75 | 0.94 | 0.66 | 0.73 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.69 | 0.90 | 0.93 | 1.00 | 0.80 | 0.85 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.71 | 0.77 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.75 | 0.86 | 0.92 | 0.95 | 0.83 | 0.86 | 0.93 |
| ar->en | 16 | 0.56 | 0.88 | 1.00 | 1.00 | 0.73 | 0.79 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.56 | 0.69 | 0.75 | 0.94 | 0.66 | 0.73 | 0.75 |
| en->en | 50 | 0.74 | 0.90 | 0.92 | 1.00 | 0.84 | 0.88 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, ar-18, x-en-ar-14, typo-06.

### FUSION GRID k=3 vector-weight=1
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.82 | 0.91 | 0.98 | 0.77 | 0.82 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 1.00 | 1.00 | 1.00 | 0.92 | 0.94 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.31 | 0.62 | 1.00 | 0.25 | 0.42 | 0.62 |
| cross_en_to_ar | 16 | 0.00 | 0.25 | 0.69 | 0.81 | 0.20 | 0.35 | 0.69 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.93 | 1.00 | 1.00 | 0.89 | 0.92 | 1.00 |
| identifier | 12 | 0.83 | 1.00 | 1.00 | 1.00 | 0.90 | 0.93 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.86 | 0.89 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 1.00 | 1.00 | 1.00 | 0.94 | 0.96 | 1.00 |
| ar->en | 16 | 0.00 | 0.31 | 0.62 | 1.00 | 0.25 | 0.42 | 0.62 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.25 | 0.69 | 0.81 | 0.20 | 0.35 | 0.69 |
| en->en | 50 | 0.82 | 0.94 | 0.98 | 1.00 | 0.90 | 0.92 | 0.98 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-05, x-en-ar-07, x-en-ar-14.

### FUSION GRID k=3 vector-weight=2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.89 | 0.94 | 0.99 | 0.82 | 0.86 | 0.94 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.96 | 1.00 | 0.83 | 0.87 | 0.96 |
| cross_ar_to_en | 16 | 0.44 | 0.81 | 0.94 | 1.00 | 0.63 | 0.72 | 0.94 |
| cross_en_to_ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.97 | 1.00 | 0.85 | 0.89 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.74 | 0.80 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 1.00 | 0.75 | 0.81 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.93 | 0.96 | 1.00 | 0.87 | 0.90 | 0.96 |
| ar->en | 16 | 0.44 | 0.81 | 0.94 | 1.00 | 0.63 | 0.72 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| en->en | 50 | 0.78 | 0.92 | 0.96 | 1.00 | 0.87 | 0.90 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-14.

### FUSION GRID k=3 vector-weight=3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.73 | 0.88 | 0.91 | 0.99 | 0.82 | 0.86 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.70 | 0.93 | 0.93 | 1.00 | 0.81 | 0.86 | 0.93 |
| cross_ar_to_en | 16 | 0.62 | 0.88 | 1.00 | 1.00 | 0.75 | 0.81 | 1.00 |
| cross_en_to_ar | 16 | 0.56 | 0.69 | 0.75 | 0.94 | 0.66 | 0.73 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 0.93 | 1.00 | 0.82 | 0.87 | 0.93 |
| identifier | 12 | 0.92 | 0.92 | 0.92 | 1.00 | 0.93 | 0.95 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.72 | 0.79 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.75 | 0.92 | 0.92 | 0.98 | 0.84 | 0.88 | 0.93 |
| ar->en | 16 | 0.62 | 0.88 | 1.00 | 1.00 | 0.75 | 0.81 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.56 | 0.69 | 0.75 | 0.94 | 0.66 | 0.73 | 0.75 |
| en->en | 50 | 0.76 | 0.90 | 0.92 | 1.00 | 0.85 | 0.89 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-14, typo-06.

### FUSION GRID k=3 vector-weight=4
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.87 | 0.91 | 0.98 | 0.81 | 0.85 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.67 | 0.85 | 0.93 | 0.96 | 0.78 | 0.83 | 0.93 |
| cross_ar_to_en | 16 | 0.62 | 0.88 | 1.00 | 1.00 | 0.77 | 0.83 | 1.00 |
| cross_en_to_ar | 16 | 0.62 | 0.69 | 0.75 | 0.94 | 0.70 | 0.75 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.69 | 0.90 | 0.93 | 1.00 | 0.80 | 0.85 | 0.93 |
| identifier | 12 | 0.83 | 0.92 | 0.92 | 1.00 | 0.89 | 0.92 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.90 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 1.00 | 0.71 | 0.77 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 0.88 | 0.65 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.74 | 0.88 | 0.92 | 0.96 | 0.83 | 0.86 | 0.93 |
| ar->en | 16 | 0.62 | 0.88 | 1.00 | 1.00 | 0.77 | 0.83 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.62 | 0.69 | 0.75 | 0.94 | 0.70 | 0.75 | 0.75 |
| en->en | 50 | 0.72 | 0.90 | 0.92 | 1.00 | 0.83 | 0.87 | 0.92 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-14, typo-06.

### full text, language-aware (arabic/english configs)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.66 | 0.74 | 0.75 | 0.78 | 0.71 | 0.73 | 0.75 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 1.00 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.97 | 0.97 | 1.00 | 0.90 | 0.92 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.94 | 0.95 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.62 | 0.62 | 0.88 | 0.79 | 0.76 | 0.75 |
| paraphrase | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 0.92 | 0.94 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 1.00 | 0.77 | 0.83 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 0.97 | 0.99 | 1.00 | 0.94 | 0.95 | 1.00 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| en->en | 50 | 0.81 | 0.94 | 0.94 | 0.99 | 0.89 | 0.91 | 0.94 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-10, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, x-en-ar-16.

### full text, simple config
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.53 | 0.66 | 0.70 | 0.74 | 0.61 | 0.64 | 0.70 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.70 | 0.93 | 0.96 | 1.00 | 0.82 | 0.87 | 0.96 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.62 | 0.79 | 0.90 | 0.97 | 0.73 | 0.78 | 0.90 |
| identifier | 12 | 0.75 | 1.00 | 1.00 | 1.00 | 0.83 | 0.88 | 1.00 |
| mixed | 4 | 0.25 | 0.25 | 0.25 | 0.50 | 0.29 | 0.34 | 0.25 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.86 | 1.00 |
| paraphrase | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| restricted | 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.17 | 0.36 | 0.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.66 | 0.71 | 0.88 |
| variant_entity | 6 | 0.67 | 0.83 | 0.83 | 0.83 | 0.75 | 0.77 | 0.83 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.76 | 0.95 | 0.97 | 1.00 | 0.87 | 0.90 | 0.98 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 0.50 | 0.50 | 0.50 | 1.00 | 0.58 | 0.68 | 0.50 |
| en->ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| en->en | 50 | 0.63 | 0.80 | 0.88 | 0.94 | 0.73 | 0.78 | 0.88 |
| en->mixed | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: en-08, x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, mix-01, mix-04, var-03, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-10, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, x-en-ar-16, typo-07.

### full text, raw (no normalization at all)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.52 | 0.64 | 0.68 | 0.73 | 0.60 | 0.63 | 0.69 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.93 | 0.96 | 1.00 | 0.86 | 0.89 | 0.96 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| digit_variant | 12 | 0.83 | 1.00 | 1.00 | 1.00 | 0.92 | 0.94 | 1.00 |
| en_factoid | 29 | 0.62 | 0.79 | 0.90 | 0.97 | 0.73 | 0.78 | 0.90 |
| identifier | 12 | 0.75 | 0.92 | 1.00 | 1.00 | 0.83 | 0.87 | 1.00 |
| mixed | 4 | 0.25 | 0.25 | 0.25 | 0.50 | 0.29 | 0.34 | 0.25 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 1.00 | 0.88 | 0.86 | 1.00 |
| paraphrase | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| restricted | 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.17 | 0.36 | 0.00 |
| typo_diacritic | 8 | 0.38 | 0.50 | 0.62 | 0.62 | 0.47 | 0.51 | 0.62 |
| variant_entity | 6 | 0.67 | 0.83 | 0.83 | 0.83 | 0.75 | 0.77 | 0.83 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.78 | 0.92 | 0.94 | 0.96 | 0.86 | 0.89 | 0.95 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 0.50 | 0.50 | 0.50 | 1.00 | 0.58 | 0.68 | 0.50 |
| en->ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| en->en | 50 | 0.59 | 0.78 | 0.88 | 0.94 | 0.71 | 0.77 | 0.88 |
| en->mixed | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **0.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: en-08, x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, mix-01, mix-04, var-03, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-10, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, x-en-ar-16, typo-01, typo-06, typo-07.

### vector, bge-m3
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.88 | 0.90 | 0.95 | 0.80 | 0.84 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.63 | 0.85 | 0.89 | 0.93 | 0.75 | 0.79 | 0.89 |
| cross_ar_to_en | 16 | 0.62 | 1.00 | 1.00 | 1.00 | 0.79 | 0.85 | 1.00 |
| cross_en_to_ar | 16 | 0.62 | 0.69 | 0.81 | 0.94 | 0.70 | 0.76 | 0.81 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.69 | 0.90 | 0.90 | 0.97 | 0.79 | 0.83 | 0.90 |
| identifier | 12 | 0.83 | 0.92 | 0.92 | 1.00 | 0.88 | 0.91 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 0.88 | 0.88 | 0.85 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 0.68 | 0.71 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.72 | 0.86 | 0.90 | 0.92 | 0.81 | 0.83 | 0.91 |
| ar->en | 16 | 0.62 | 1.00 | 1.00 | 1.00 | 0.79 | 0.85 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.62 | 0.69 | 0.81 | 0.94 | 0.70 | 0.76 | 0.81 |
| en->en | 50 | 0.72 | 0.90 | 0.90 | 0.98 | 0.82 | 0.86 | 0.90 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, en-28, ar-18, x-en-ar-14, para-04, typo-06.

### vector, bge-m3, query digits NOT folded
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.88 | 0.90 | 0.95 | 0.80 | 0.84 | 0.91 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.63 | 0.85 | 0.89 | 0.93 | 0.75 | 0.79 | 0.89 |
| cross_ar_to_en | 16 | 0.62 | 1.00 | 1.00 | 1.00 | 0.79 | 0.85 | 1.00 |
| cross_en_to_ar | 16 | 0.62 | 0.69 | 0.81 | 0.94 | 0.70 | 0.76 | 0.81 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.69 | 0.90 | 0.90 | 0.97 | 0.79 | 0.83 | 0.90 |
| identifier | 12 | 0.83 | 0.92 | 0.92 | 1.00 | 0.88 | 0.91 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 0.88 | 0.88 | 0.88 | 0.88 | 0.85 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 0.68 | 0.71 | 0.67 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.75 | 0.88 | 0.88 | 0.64 | 0.70 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.72 | 0.86 | 0.90 | 0.92 | 0.81 | 0.83 | 0.91 |
| ar->en | 16 | 0.62 | 1.00 | 1.00 | 1.00 | 0.79 | 0.85 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.62 | 0.69 | 0.81 | 0.94 | 0.70 | 0.76 | 0.81 |
| en->en | 50 | 0.72 | 0.90 | 0.90 | 0.98 | 0.82 | 0.86 | 0.90 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **0.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, en-28, ar-18, x-en-ar-14, para-04, typo-06.

### hybrid RRF, bge-m3 + full text (language-aware)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.65 | 0.72 | 0.77 | 0.79 | 0.71 | 0.73 | 0.77 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.85 | 0.93 | 1.00 | 1.00 | 0.91 | 0.93 | 1.00 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 0.90 | 0.93 | 1.00 | 0.88 | 0.91 | 0.93 |
| identifier | 12 | 0.83 | 0.92 | 1.00 | 1.00 | 0.89 | 0.92 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 0.88 | 1.00 | 1.00 | 1.00 | 0.94 | 1.00 |
| paraphrase | 6 | 0.67 | 0.83 | 1.00 | 1.00 | 0.78 | 0.84 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.75 | 0.88 | 0.88 | 0.88 | 0.81 | 0.83 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.85 | 0.95 | 0.98 | 0.98 | 0.92 | 0.93 | 0.98 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.06 | 0.12 | 0.25 | 0.05 | 0.10 | 0.12 |
| en->en | 50 | 0.82 | 0.89 | 0.96 | 1.00 | 0.89 | 0.91 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-13, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, typo-06.

### hybrid RRF, bge-m3 + full text (simple)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.87 | 0.94 | 0.97 | 0.81 | 0.85 | 0.94 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.93 | 0.93 | 0.82 | 0.85 | 0.93 |
| cross_ar_to_en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.66 | 0.74 | 0.94 |
| cross_en_to_ar | 16 | 0.50 | 0.69 | 0.75 | 0.88 | 0.62 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 1.00 | 1.00 | 0.83 | 0.87 | 1.00 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| multi_passage | 4 | 0.38 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 1.00 | 1.00 | 0.75 | 0.81 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.75 | 0.88 | 1.00 | 0.72 | 0.79 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.93 | 0.95 | 0.96 | 0.86 | 0.89 | 0.95 |
| ar->en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.66 | 0.74 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.50 | 0.69 | 0.75 | 0.88 | 0.62 | 0.68 | 0.75 |
| en->en | 50 | 0.76 | 0.88 | 1.00 | 1.00 | 0.85 | 0.89 | 1.00 |
| en->mixed | 2 | 0.50 | 1.00 | 1.00 | 1.00 | 0.75 | 0.82 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-05, ar-18, x-en-ar-14.

### hybrid RRF, bge-m3 + full text (raw)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.87 | 0.94 | 0.96 | 0.81 | 0.85 | 0.94 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.93 | 0.93 | 0.82 | 0.85 | 0.93 |
| cross_ar_to_en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.66 | 0.74 | 0.94 |
| cross_en_to_ar | 16 | 0.50 | 0.69 | 0.75 | 0.88 | 0.62 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.90 | 1.00 | 1.00 | 0.83 | 0.87 | 1.00 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| multi_passage | 4 | 0.38 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 1.00 | 1.00 | 0.75 | 0.81 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.62 | 0.75 | 0.88 | 0.67 | 0.72 | 0.75 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.91 | 0.93 | 0.95 | 0.86 | 0.88 | 0.93 |
| ar->en | 16 | 0.50 | 0.81 | 0.94 | 1.00 | 0.66 | 0.74 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.50 | 0.69 | 0.75 | 0.88 | 0.62 | 0.68 | 0.75 |
| en->en | 50 | 0.76 | 0.88 | 1.00 | 1.00 | 0.85 | 0.89 | 1.00 |
| en->mixed | 2 | 0.50 | 1.00 | 1.00 | 1.00 | 0.75 | 0.82 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **0.25**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-05, ar-18, x-en-ar-14, typo-06.

### hybrid RRF, bge-m3 + full text (language-aware), chosen k/weight
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.89 | 0.94 | 0.99 | 0.82 | 0.86 | 0.94 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.96 | 1.00 | 0.83 | 0.87 | 0.96 |
| cross_ar_to_en | 16 | 0.44 | 0.81 | 0.94 | 1.00 | 0.63 | 0.72 | 0.94 |
| cross_en_to_ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.97 | 1.00 | 0.85 | 0.89 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.74 | 0.80 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 1.00 | 0.75 | 0.81 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.79 | 0.93 | 0.96 | 1.00 | 0.87 | 0.90 | 0.96 |
| ar->en | 16 | 0.44 | 0.81 | 0.94 | 1.00 | 0.63 | 0.72 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| en->en | 50 | 0.78 | 0.92 | 0.96 | 1.00 | 0.87 | 0.90 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-14.

### vector, multilingual-e5-large
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.72 | 0.82 | 0.87 | 0.93 | 0.78 | 0.82 | 0.87 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.78 | 0.93 | 0.96 | 1.00 | 0.84 | 0.88 | 0.96 |
| cross_ar_to_en | 16 | 0.12 | 0.12 | 0.31 | 0.56 | 0.19 | 0.28 | 0.31 |
| cross_en_to_ar | 16 | 0.44 | 0.56 | 0.62 | 0.88 | 0.54 | 0.61 | 0.62 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.79 | 0.93 | 1.00 | 1.00 | 0.87 | 0.90 | 1.00 |
| identifier | 12 | 0.92 | 1.00 | 1.00 | 1.00 | 0.96 | 0.97 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| paraphrase | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 0.92 | 0.94 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.88 | 0.88 | 0.88 | 0.88 | 0.88 | 0.88 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.85 | 0.95 | 0.96 | 0.98 | 0.91 | 0.92 | 0.96 |
| ar->en | 16 | 0.12 | 0.12 | 0.31 | 0.56 | 0.19 | 0.28 | 0.31 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.56 | 0.62 | 0.88 | 0.54 | 0.61 | 0.62 |
| en->en | 50 | 0.82 | 0.96 | 1.00 | 1.00 | 0.90 | 0.93 | 1.00 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-05, x-ar-en-08, x-en-ar-04, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-14, typo-06.

### hybrid RRF, multilingual-e5-large + full text (language-aware)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.71 | 0.84 | 0.86 | 0.89 | 0.78 | 0.81 | 0.86 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.81 | 0.96 | 1.00 | 1.00 | 0.89 | 0.92 | 1.00 |
| cross_ar_to_en | 16 | 0.06 | 0.12 | 0.12 | 0.38 | 0.13 | 0.18 | 0.12 |
| cross_en_to_ar | 16 | 0.19 | 0.50 | 0.62 | 0.69 | 0.38 | 0.45 | 0.62 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.83 | 1.00 | 1.00 | 1.00 | 0.90 | 0.92 | 1.00 |
| identifier | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| paraphrase | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.88 | 1.00 | 1.00 | 1.00 | 0.92 | 0.94 | 1.00 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.87 | 0.98 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| ar->en | 16 | 0.06 | 0.12 | 0.12 | 0.38 | 0.13 | 0.18 | 0.12 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.19 | 0.50 | 0.62 | 0.69 | 0.38 | 0.45 | 0.62 |
| en->en | 50 | 0.88 | 1.00 | 1.00 | 1.00 | 0.94 | 0.96 | 1.00 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-05, x-ar-en-08, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-ar-en-09, x-ar-en-10, x-ar-en-11, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-14.

### vector, Arabic-Triplet-Matryoshka-V2
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.38 | 0.56 | 0.60 | 0.71 | 0.48 | 0.54 | 0.60 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.52 | 0.81 | 0.89 | 0.93 | 0.66 | 0.72 | 0.89 |
| cross_ar_to_en | 16 | 0.00 | 0.06 | 0.06 | 0.38 | 0.06 | 0.13 | 0.06 |
| cross_en_to_ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| digit_variant | 12 | 0.50 | 1.00 | 1.00 | 1.00 | 0.71 | 0.78 | 1.00 |
| en_factoid | 29 | 0.59 | 0.69 | 0.72 | 0.90 | 0.66 | 0.72 | 0.72 |
| identifier | 12 | 0.17 | 0.42 | 0.50 | 0.58 | 0.30 | 0.37 | 0.50 |
| mixed | 4 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 |
| multi_passage | 4 | 0.38 | 0.62 | 0.62 | 0.88 | 0.78 | 0.75 | 0.75 |
| paraphrase | 6 | 0.33 | 0.50 | 0.67 | 0.83 | 0.48 | 0.56 | 0.67 |
| restricted | 1 | 0.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.63 | 1.00 |
| typo_diacritic | 8 | 0.38 | 0.50 | 0.62 | 0.75 | 0.46 | 0.53 | 0.62 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.49 | 0.77 | 0.85 | 0.89 | 0.65 | 0.70 | 0.85 |
| ar->en | 16 | 0.00 | 0.06 | 0.06 | 0.38 | 0.06 | 0.13 | 0.06 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.00 | 0.00 | 0.06 | 0.01 | 0.02 | 0.00 |
| en->en | 50 | 0.49 | 0.66 | 0.70 | 0.85 | 0.59 | 0.65 | 0.70 |
| en->mixed | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: en-07, en-12, ar-06, x-ar-en-01, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-03, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, mix-01, mix-04, en-29, ar-18, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-14, x-ar-en-16, x-en-ar-09, x-en-ar-10, x-en-ar-11, x-en-ar-13, x-en-ar-14, x-en-ar-15, x-en-ar-16, id-04, id-05, id-07, id-10, id-12, para-02, typo-01, typo-06.

### hybrid RRF, Arabic-Triplet-Matryoshka-V2 + full text (language-aware)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.44 | 0.64 | 0.74 | 0.79 | 0.56 | 0.61 | 0.74 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.59 | 0.85 | 0.96 | 1.00 | 0.73 | 0.80 | 0.96 |
| cross_ar_to_en | 16 | 0.00 | 0.00 | 0.00 | 0.19 | 0.02 | 0.06 | 0.00 |
| cross_en_to_ar | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| digit_variant | 12 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| en_factoid | 29 | 0.66 | 0.86 | 0.97 | 1.00 | 0.76 | 0.82 | 0.97 |
| identifier | 12 | 0.17 | 0.58 | 1.00 | 1.00 | 0.42 | 0.56 | 1.00 |
| mixed | 4 | 0.50 | 0.50 | 1.00 | 1.00 | 0.61 | 0.70 | 1.00 |
| multi_passage | 4 | 0.38 | 0.75 | 0.75 | 0.75 | 0.75 | 0.73 | 0.75 |
| paraphrase | 6 | 0.50 | 0.83 | 0.83 | 1.00 | 0.67 | 0.75 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.38 | 0.75 | 0.88 | 1.00 | 0.57 | 0.68 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.58 | 0.85 | 0.96 | 1.00 | 0.74 | 0.80 | 0.96 |
| ar->en | 16 | 0.00 | 0.00 | 0.00 | 0.19 | 0.02 | 0.06 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| en->en | 50 | 0.57 | 0.82 | 0.94 | 0.98 | 0.71 | 0.77 | 0.94 |
| en->mixed | 2 | 0.00 | 0.00 | 1.00 | 1.00 | 0.23 | 0.41 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-03, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, x-ar-en-10, x-ar-en-11, x-ar-en-12, x-ar-en-14, x-ar-en-15, x-ar-en-16, x-en-ar-09, x-en-ar-10, x-en-ar-11, x-en-ar-12, x-en-ar-13, x-en-ar-14, x-en-ar-15, x-en-ar-16, multi-01.

### hybrid RRF, all embedders + full text (ensemble)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.70 | 0.83 | 0.92 | 0.97 | 0.80 | 0.84 | 0.92 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.81 | 0.93 | 0.96 | 0.96 | 0.88 | 0.90 | 0.96 |
| cross_ar_to_en | 16 | 0.06 | 0.19 | 0.81 | 1.00 | 0.30 | 0.46 | 0.81 |
| cross_en_to_ar | 16 | 0.25 | 0.62 | 0.69 | 0.81 | 0.46 | 0.55 | 0.69 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.86 | 0.97 | 1.00 | 1.00 | 0.91 | 0.93 | 1.00 |
| identifier | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.86 | 0.89 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 1.00 | 0.76 | 0.82 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.85 | 0.95 | 0.96 | 0.98 | 0.92 | 0.93 | 0.96 |
| ar->en | 16 | 0.06 | 0.19 | 0.81 | 1.00 | 0.30 | 0.46 | 0.81 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.25 | 0.62 | 0.69 | 0.81 | 0.46 | 0.55 | 0.69 |
| en->en | 50 | 0.86 | 0.96 | 0.98 | 1.00 | 0.92 | 0.94 | 0.98 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-05, x-en-ar-07, x-en-ar-14.

### language-routed: Arabic questions use the ensemble, English the primary hybrid
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.70 | 0.82 | 0.92 | 0.99 | 0.80 | 0.84 | 0.92 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.81 | 0.93 | 0.96 | 0.96 | 0.88 | 0.90 | 0.96 |
| cross_ar_to_en | 16 | 0.06 | 0.19 | 0.81 | 1.00 | 0.30 | 0.46 | 0.81 |
| cross_en_to_ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.76 | 0.93 | 0.97 | 1.00 | 0.85 | 0.89 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 |
| paraphrase | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.86 | 0.89 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.62 | 0.88 | 0.88 | 1.00 | 0.76 | 0.82 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.85 | 0.95 | 0.96 | 0.98 | 0.92 | 0.93 | 0.96 |
| ar->en | 16 | 0.06 | 0.19 | 0.81 | 1.00 | 0.30 | 0.46 | 0.81 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| en->en | 50 | 0.78 | 0.92 | 0.96 | 1.00 | 0.87 | 0.90 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: ar-06, x-en-ar-14.

### PRODUCT: POST /search (pgvector HNSW + full text, RRF, permission-filtered)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 141 | 0.70 | 0.87 | 0.94 | 0.99 | 0.81 | 0.85 | 0.94 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 27 | 0.74 | 0.93 | 0.96 | 1.00 | 0.83 | 0.87 | 0.96 |
| cross_ar_to_en | 16 | 0.44 | 0.69 | 0.94 | 1.00 | 0.62 | 0.72 | 0.94 |
| cross_en_to_ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 29 | 0.72 | 0.93 | 0.97 | 1.00 | 0.83 | 0.87 | 0.97 |
| identifier | 12 | 0.92 | 0.92 | 1.00 | 1.00 | 0.93 | 0.95 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_passage | 4 | 0.38 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |
| paraphrase | 6 | 0.67 | 0.67 | 0.83 | 1.00 | 0.74 | 0.80 | 0.83 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| typo_diacritic | 8 | 0.50 | 0.88 | 0.88 | 1.00 | 0.67 | 0.75 | 0.88 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 55 | 0.77 | 0.93 | 0.96 | 1.00 | 0.86 | 0.89 | 0.96 |
| ar->en | 16 | 0.44 | 0.69 | 0.94 | 1.00 | 0.62 | 0.72 | 0.94 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 16 | 0.44 | 0.69 | 0.75 | 0.94 | 0.60 | 0.68 | 0.75 |
| en->en | 50 | 0.76 | 0.92 | 0.96 | 1.00 | 0.86 | 0.89 | 0.96 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 10. Answerable questions with no relevant chunk in the top 10: x-en-ar-14.

