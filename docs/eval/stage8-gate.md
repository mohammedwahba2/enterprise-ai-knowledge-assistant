# Stage 8: retrieval gate calibration
Generated 2026-11-14 by `EVAL_LIVE_OLLAMA=1 pytest tests/test_eval_stage8.py -k gate`.
- Score: the highest cosine similarity (bge-m3) among the 6 passages the model would be shown, from the asking user's point of view (a viewer never retrieves the restricted board minutes).
- Questions: 223 (150 answerable, 73 unanswerable), split deterministically and stratified: 112 calibration, 111 test. **The threshold was chosen on the calibration split only** (highest refusal recall with false refusals <= 5%) and then measured once on the test split.
- AUC: calibration 0.627, test 0.780 (probability that an answerable question scores above an unanswerable one).

**Chosen threshold: 0.409**

| split | n answerable | n unanswerable | gate refusal recall (unanswerable) | false refusals (answerable) |
|---|---|---|---|---|
| calibration | 75 | 37 | 0.05 | 0.04 |
| test (held out) | 75 | 36 | 0.17 | 0.01 |

Gate refusal recall by kind on the test split (the model's own NO_ANSWER and the citation verifier catch more; end-to-end numbers are in stage8-answers.md):

| kind | refused by the gate |
|---|---|
| absent | 0/11 |
| near_miss | 0/5 |
| off_topic | 5/5 |
| plausible_absent | 0/7 |
| restricted_only | 1/5 |

All questions, by threshold (for reading the trade-off, not for choosing it):

| threshold | unanswerable refused | answerable refused |
|---|---|---|
| 0.20 | 0.00 | 0.00 |
| 0.25 | 0.00 | 0.00 |
| 0.30 | 0.01 | 0.00 |
| 0.35 | 0.07 | 0.00 |
| 0.40 | 0.11 | 0.02 |
| 0.45 | 0.16 | 0.08 |
| 0.50 | 0.45 | 0.18 |
| 0.55 | 0.74 | 0.36 |
| 0.60 | 0.85 | 0.64 |
| 0.65 | 0.95 | 0.81 |
