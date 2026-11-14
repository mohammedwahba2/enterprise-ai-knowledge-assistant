# Stage 6 retrieval baseline

Generated 2026-11-14 by `EVAL_LIVE_OLLAMA=1 pytest tests/test_eval_baselines.py`. **Foundation numbers, not the stage-7 evaluation.**

- Corpus: 34 synthetic documents (24 are near-duplicate subsidiary variants used as hard negatives), each about one chunk.
- Questions: 69 (63 answerable).
- Retrieval is unfiltered (no permissions), single-stage (no fusion, no reranker): the product path is stage 7.
- Small corpus: differences of a few points are noise; read the cross-lingual rows and the large gaps.

### vector, bge-m3 (Ollama)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 63 | 0.70 | 0.90 | 0.95 | 0.98 | 0.81 | 0.85 | 0.95 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 12 | 0.58 | 0.83 | 0.92 | 0.92 | 0.71 | 0.76 | 0.92 |
| cross_ar_to_en | 8 | 0.50 | 1.00 | 1.00 | 1.00 | 0.73 | 0.80 | 1.00 |
| cross_en_to_ar | 8 | 0.38 | 0.50 | 0.75 | 1.00 | 0.54 | 0.65 | 0.75 |
| digit_variant | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en_factoid | 12 | 0.58 | 1.00 | 1.00 | 1.00 | 0.76 | 0.82 | 1.00 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 24 | 0.79 | 0.92 | 0.96 | 0.96 | 0.86 | 0.88 | 0.96 |
| ar->en | 8 | 0.50 | 1.00 | 1.00 | 1.00 | 0.73 | 0.80 | 1.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 8 | 0.38 | 0.50 | 0.75 | 1.00 | 0.54 | 0.65 | 0.75 |
| en->en | 19 | 0.74 | 1.00 | 1.00 | 1.00 | 0.85 | 0.89 | 1.00 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 6. Answerable questions with no relevant chunk in the top 10: ar-06.

### full text, language-aware (arabic/english)
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 63 | 0.56 | 0.67 | 0.73 | 0.76 | 0.63 | 0.66 | 0.73 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 12 | 0.42 | 0.67 | 1.00 | 1.00 | 0.62 | 0.72 | 1.00 |
| cross_ar_to_en | 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 8 | 0.00 | 0.00 | 0.00 | 0.12 | 0.02 | 0.04 | 0.00 |
| digit_variant | 12 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| en_factoid | 12 | 0.83 | 0.92 | 0.92 | 1.00 | 0.88 | 0.91 | 0.92 |
| mixed | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| restricted | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| variant_entity | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 24 | 0.58 | 0.83 | 1.00 | 1.00 | 0.75 | 0.81 | 1.00 |
| ar->en | 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| en->ar | 8 | 0.00 | 0.00 | 0.00 | 0.12 | 0.02 | 0.04 | 0.00 |
| en->en | 19 | 0.89 | 0.95 | 0.95 | 1.00 | 0.93 | 0.94 | 0.95 |
| en->mixed | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 6. Answerable questions with no relevant chunk in the top 10: x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08.

### full text, simple
| overall | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| all | 63 | 0.29 | 0.60 | 0.65 | 0.70 | 0.45 | 0.51 | 0.65 |

| category | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar_factoid | 12 | 0.08 | 0.83 | 0.92 | 1.00 | 0.48 | 0.61 | 0.92 |
| cross_ar_to_en | 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_en_to_ar | 8 | 0.00 | 0.00 | 0.00 | 0.12 | 0.02 | 0.04 | 0.00 |
| digit_variant | 12 | 0.75 | 1.00 | 1.00 | 1.00 | 0.88 | 0.91 | 1.00 |
| en_factoid | 12 | 0.25 | 0.75 | 0.83 | 0.83 | 0.45 | 0.55 | 0.83 |
| mixed | 4 | 0.25 | 0.25 | 0.50 | 0.75 | 0.33 | 0.42 | 0.50 |
| restricted | 1 | 0.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.63 | 1.00 |
| variant_entity | 6 | 0.67 | 0.83 | 0.83 | 0.83 | 0.75 | 0.77 | 0.83 |

| language pair | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | nDCG@10 | page-hit@5 |
|---|---|---|---|---|---|---|---|
| ar->ar | 24 | 0.38 | 0.92 | 0.96 | 1.00 | 0.66 | 0.74 | 0.96 |
| ar->en | 8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ar->mixed | 2 | 0.50 | 0.50 | 1.00 | 1.00 | 0.60 | 0.69 | 1.00 |
| en->ar | 8 | 0.00 | 0.00 | 0.00 | 0.12 | 0.02 | 0.04 | 0.00 |
| en->en | 19 | 0.42 | 0.79 | 0.84 | 0.84 | 0.57 | 0.64 | 0.84 |
| en->mixed | 2 | 0.00 | 0.00 | 0.00 | 0.50 | 0.06 | 0.15 | 0.00 |

Digit-variant consistency (identical top-10 for Western / Arabic-Indic / Persian digits): **1.00**

Unanswerable questions (not scored here): 6. Answerable questions with no relevant chunk in the top 10: en-08, en-11, x-ar-en-01, x-ar-en-02, x-ar-en-03, x-ar-en-04, x-ar-en-05, x-ar-en-06, x-ar-en-07, x-ar-en-08, x-en-ar-01, x-en-ar-02, x-en-ar-04, x-en-ar-05, x-en-ar-06, x-en-ar-07, x-en-ar-08, mix-04, var-03.

