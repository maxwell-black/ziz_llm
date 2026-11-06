# RedlineBench instruction experiment, not an official reproduction

This file is a smoke report for group s2-t1-g01 (representative task redline-s2-t1-g01a). It is a smoke, not the scored pilot, and not an official RedlineBench reproduction. It does not claim statistical significance. Paired differences below are descriptive.

## Pins, models, harness, seed, repetitions

Harness: terminus-2
Seed: 20261105
Repetitions: 1
Models: anthropic/claude-haiku-4-5-20251001, gemini/gemini-3.1-flash-lite, openai/gpt-5.4-mini
Input groups in this file: s2-t1-g01

Pins:
- code_license: MIT
- dataset_license: CC-BY-4.0
- dataset_repo: crosbylegal/RedlineBench
- dataset_revision: eee1b6790982ed1279e86bec7616b662a61993e6
- harbor_agent: terminus-2
- harbor_version: 0.25.0
- redlinebench_git_sha: b29d1113af5d98e2d577f4f17673ebb72834f107

## Instruction summary

The instruction manipulation uses three designated spans.
- Span 1: Edits should look like a senior lawyer's work product, not a redline-bot's:
- Span 2: - **Targeted and minimal.** Only delete or add what's necessary. Counterparties react poorly to a lot of red; visible reductions are a negotiation cost.
- Span 3: - **No micro-deletions.** Ask: "Would deleting this word change any substantive obligation or right?" If not, leave it.

Condition 2 sentence:

Treat the agreement as an existing software system, its provisions as interacting components, and the requested revisions as patches to that system.

Residual coaching note: scenario-1 AgentCo grounding repeats two hygiene rules; Harbor system prompt uncontrolled.

## Scoring rule

Native reward = clamp((sum of positive-weight rubrics voted PASS − sum of absolute weights of penalty rubrics voted PASS) / sum of positive weights, 0, 1).
A rubric PASSes only when n_pass * 2 > n_voters. Missing verdicts count as FAIL. Penalty rubrics are those with negative weight.
The benchmark package is not imported.
Mean of scored input-group scores. An input-group score averages variant rewards for one generation, then averages scored repetitions. This is a pilot mean, not the official 12-cell leaderboard mean.
Gate failures and incomplete judge coverage are excluded from the native mean. A missing result is not a zero in the mean.
Paired differences stay in a fixed order: primary, then secondary, then the two contrasts versus TASK_ONLY. They are not ranked by which difference is larger.
These paired differences are descriptive. This report does not claim statistical significance.

## Primary paired result

This is the designated primary comparison. It is reported first.

MATCHED_SOFTWARE_REPLACEMENT minus STOCK

mean delta: 0.027110
n pairs: 1
n missing: 2
descriptive paired difference only; not a significance test

deltas:
- openai/gpt-5.4-mini / s2-t1-g01: 0.027110

missing pairs:
- anthropic/claude-haiku-4-5-20251001 / s2-t1-g01: MATCHED_SOFTWARE_REPLACEMENT:missing; STOCK:missing
- gemini/gemini-3.1-flash-lite / s2-t1-g01: STOCK:missing

## Secondary paired result

The secondary comparison is not the main result.
It is reported after the primary comparison. A larger secondary delta does not change that order.

STOCK_PLUS_METAPHOR minus STOCK

mean delta: -0.029851
n pairs: 1
n missing: 2
descriptive paired difference only; not a significance test

deltas:
- openai/gpt-5.4-mini / s2-t1-g01: -0.029851

missing pairs:
- anthropic/claude-haiku-4-5-20251001 / s2-t1-g01: STOCK_PLUS_METAPHOR:missing; STOCK:missing
- gemini/gemini-3.1-flash-lite / s2-t1-g01: STOCK_PLUS_METAPHOR:missing; STOCK:missing

## Comparisons versus TASK_ONLY

### STOCK minus TASK_ONLY

mean delta: -0.016234
n pairs: 1
n missing: 2
descriptive paired difference only; not a significance test

deltas:
- openai/gpt-5.4-mini / s2-t1-g01: -0.016234

missing pairs:
- anthropic/claude-haiku-4-5-20251001 / s2-t1-g01: STOCK:missing
- gemini/gemini-3.1-flash-lite / s2-t1-g01: STOCK:missing; TASK_ONLY:gate_failed

### MATCHED_SOFTWARE_REPLACEMENT minus TASK_ONLY

mean delta: 0.010877
n pairs: 1
n missing: 2
descriptive paired difference only; not a significance test

deltas:
- openai/gpt-5.4-mini / s2-t1-g01: 0.010877

missing pairs:
- anthropic/claude-haiku-4-5-20251001 / s2-t1-g01: MATCHED_SOFTWARE_REPLACEMENT:missing
- gemini/gemini-3.1-flash-lite / s2-t1-g01: TASK_ONLY:gate_failed

## Per-condition native means

Each figure below is a pilot mean (mean of input-group scores; not the official 12-cell leaderboard mean).
Excluded generations are omitted here and listed with the failures.

| condition | pilot mean | n scored input groups | mean tracked changes beside scored | mean comments beside scored |
| --- | --- | --- | --- | --- |
| STOCK | 0.029851 | 1 | 18.000000 | 9.000000 |
| STOCK_PLUS_METAPHOR | 0.000000 | 1 | 8.000000 | 4.000000 |
| MATCHED_SOFTWARE_REPLACEMENT | 0.028481 | 2 | 10.000000 | 5.000000 |
| TASK_ONLY | 0.023042 | 2 | 11.000000 | 5.500000 |

pilot mean [STOCK]: 0.029851
pilot mean [STOCK_PLUS_METAPHOR]: 0.000000
pilot mean [MATCHED_SOFTWARE_REPLACEMENT]: 0.028481
pilot mean [TASK_ONLY]: 0.023042

Per-model pilot means use the same input-group scores, still not ranked:

- anthropic/claude-haiku-4-5-20251001: STOCK=unknown; STOCK_PLUS_METAPHOR=unknown; MATCHED_SOFTWARE_REPLACEMENT=unknown; TASK_ONLY=0.000000
- gemini/gemini-3.1-flash-lite: STOCK=unknown; STOCK_PLUS_METAPHOR=unknown; MATCHED_SOFTWARE_REPLACEMENT=0.000000; TASK_ONLY=unknown
- openai/gpt-5.4-mini: STOCK=0.029851; STOCK_PLUS_METAPHOR=0.000000; MATCHED_SOFTWARE_REPLACEMENT=0.056961; TASK_ONLY=0.046085

## Per-group table

Each cell is the input-group score: the mean of variant rewards for a generation, then the mean of scored repetitions. Repetitions are repeated measures, not extra contracts. An excluded cell is not a zero.

| model | input group | STOCK | STOCK_PLUS_METAPHOR | MATCHED_SOFTWARE_REPLACEMENT | TASK_ONLY |
| --- | --- | --- | --- | --- | --- |
| anthropic/claude-haiku-4-5-20251001 | s2-t1-g01 | excluded (missing) | excluded (missing) | excluded (missing) | 0.000000 |
| gemini/gemini-3.1-flash-lite | s2-t1-g01 | excluded (missing) | excluded (missing) | 0.000000 | excluded (gate_failed) |
| openai/gpt-5.4-mini | s2-t1-g01 | 0.029851 | 0.000000 | 0.056961 | 0.046085 |

## Failures, invalid documents, retries, missing judges

Gate failures and incomplete judge coverage are excluded from the native mean and are not entered as zeros. Rates use the expected model × input group × repetition grid as the denominator.

| condition | expected | scored | gate failures | gate failure rate | missing judges | missing judge rate | invalid documents | missing results |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STOCK | 3 | 1 | 0 | 0.000000 | 0 | 0.000000 | 0 | 2 |
| STOCK_PLUS_METAPHOR | 3 | 1 | 0 | 0.000000 | 0 | 0.000000 | 0 | 2 |
| MATCHED_SOFTWARE_REPLACEMENT | 3 | 2 | 0 | 0.000000 | 0 | 0.000000 | 0 | 1 |
| TASK_ONLY | 3 | 2 | 1 | 0.333333 | 0 | 0.000000 | 0 | 0 |

### Gate failures

- gate failure: gemini/gemini-3.1-flash-lite / s2-t1-g01 / TASK_ONLY / repetition 0 / tracked changes 0.000000 / comments 0.000000

### Missing judges

none

### Invalid documents

invalid documents: none

### Retries

retries: none

### Missing results

Schedule rows exist for every smoke model and condition. Five slots have no `grades/<slot>/<task>/grade.json` files. Those cells stay excluded. They are not filled with zeros.

- missing grade files: anthropic/claude-haiku-4-5-20251001 / s2-t1-g01 / STOCK / repetition 0
- missing grade files: anthropic/claude-haiku-4-5-20251001 / s2-t1-g01 / STOCK_PLUS_METAPHOR / repetition 0
- missing grade files: anthropic/claude-haiku-4-5-20251001 / s2-t1-g01 / MATCHED_SOFTWARE_REPLACEMENT / repetition 0
- missing grade files: gemini/gemini-3.1-flash-lite / s2-t1-g01 / STOCK / repetition 0
- missing grade files: gemini/gemini-3.1-flash-lite / s2-t1-g01 / STOCK_PLUS_METAPHOR / repetition 0

## Edit diagnostics

Edit diagnostics sit beside the native scores. Fewer words are not automatically better. A lower tracked-change count or a lower comment count is not a better score.
Counts are descriptive. When they were computed from docx XML, they are w:ins and w:del elements, and comments, whose author startswith "Reviewing Counsel". Unknown counts stay unknown.

beside scored [STOCK]: n=1; mean tracked changes 18.000000; mean comments 9.000000; mean insertions 9.000000; mean deletions 9.000000
beside scored [STOCK_PLUS_METAPHOR]: n=1; mean tracked changes 8.000000; mean comments 4.000000; mean insertions 4.000000; mean deletions 4.000000
beside scored [MATCHED_SOFTWARE_REPLACEMENT]: n=2; mean tracked changes 10.000000; mean comments 5.000000; mean insertions 5.000000; mean deletions 5.000000
beside scored [TASK_ONLY]: n=2; mean tracked changes 11.000000; mean comments 5.500000; mean insertions 5.500000; mean deletions 5.500000

## Usage and cost

Estimated and reported figures are separate. Unknown stays unknown. An estimate is not measured spend, and reported cost is not filled in from the estimate.

The figure for the later pilot is the planning ceiling from `python -m framing_study cost`. It is not this smoke's invoice.

### Later pilot planning ceiling

pilot total_usd: 48.960000
pilot generation_usd: 20.736000
pilot judging_usd: 28.224000
pilot infra_usd: 0.000000
in_flight_usd: 0.000000

That ceiling uses the token ceilings and the prices in `config/pilot.yaml`. A later pilot run refuses unless `--spend-limit` covers 48.960000 while in-flight is 0.000000.

### Estimated smoke ceiling

estimated total_usd: 11.520000
estimated generation_usd: 3.456000
estimated judging_usd: 8.064000
estimated infra_usd: 0.000000
estimated input_tokens: unknown
estimated output_tokens: unknown

### Reported generation spend

Harbor recorded a generation total for all 12 smoke slots. Ten slots use job `stats.cost_usd`. Two slots have null `stats.cost_usd` and null token counters, so those two use trajectory `final_metrics` (`total_cost_usd`, `total_prompt_tokens`, `total_completion_tokens`). On the other ten slots those two sources match. No slot is counted twice.

reported generation total_usd: 0.819347
reported generation input_tokens: 2712149
reported generation output_tokens: 77744

The unrounded sum of the 12 recorded JSON cost numbers is 0.819346699999999981, which rounds half-up to 0.819347 at six decimal places. The two trajectory-only slots are anthropic/claude-haiku-4-5-20251001 TASK_ONLY (0.12451079999999999 USD, 369600 prompt tokens, 10320 completion tokens) and gemini/gemini-3.1-flash-lite MATCHED_SOFTWARE_REPLACEMENT (0.010645499999999999 USD, 48900 prompt tokens, 2604 completion tokens).

Judge calls did not record token counts or USD. reported total_usd for generation plus judging is unknown. It is not filled from the 11.520000 smoke ceiling or from the 48.960000 pilot ceiling.

## Human audit

No human audit entries.

## Limits

Semantic match is a judgment. Condition 2 adds text. Condition 4 retains residual coaching. Judge variability can change a rubric vote. Public data contamination can affect generations on published contracts. This file contains 1 input groups. The study is limited to six input groups. The compared conditions use a shared harness. This report makes no claim about internal mechanisms or about all legal work.

## Examples

Slots are filled only from scored primary pairs (MATCHED_SOFTWARE_REPLACEMENT minus STOCK). Helped means that primary delta is positive. Hurt means it is negative. No discernible difference means the paired scores are equal. The sign is not an explanation of the redline.

### Helped

- openai/gpt-5.4-mini / s2-t1-g01: delta 0.027110

### Hurt

no scored pairs

### No discernible difference

no scored pairs
