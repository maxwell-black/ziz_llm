# RedlineBench instruction map

Version-controlled map for the framing-study experiment. The runnable edits are `framing_study.transform.transform`. Span strings and condition names live in `framing_study.pins` (worker-docs). This map does not copy rubric text. Semantic match between a legal span and its software sentence is a judgment.

This study is the four-condition RedlineBench instruction experiment. It is separate from the `framing-experiment` package in this checkout.

## Pins

| Pin | Value |
| --- | --- |
| Code | `https://github.com/crosbylegal/redline-bench` at `b29d1113af5d98e2d577f4f17673ebb72834f107` (2026-10-02, "Merge pull request #13 from crosbylegal/sharan-strip-provider") |
| Dataset | Hugging Face `crosbylegal/RedlineBench` at `eee1b6790982ed1279e86bec7616b662a61993e6` |
| Conditions | `STOCK`, `STOCK_PLUS_METAPHOR`, `MATCHED_SOFTWARE_REPLACEMENT`, `TASK_ONLY` |
| Metaphor sentence | Treat the agreement as an existing software system, its provisions as interacting components, and the requested revisions as patches to that system. |
| Heading | `## Redlining hygiene` |
| D1 original | Edits should look like a senior lawyer's work product, not a redline-bot's: |
| D1 software | Edits should look like a senior engineer's work product, not a rewrite-bot's: |
| D2 original | `- **Targeted and minimal.** Only delete or add what's necessary. Counterparties react poorly to a lot of red; visible reductions are a negotiation cost.` |
| D2 software | `- **Targeted and minimal.** Only delete or add what's necessary. The other party reacts poorly to a large diff; extra visible changes carry a real cost.` |
| D3 original | `- **No micro-deletions.** Ask: "Would deleting this word change any substantive obligation or right?" If not, leave it.` |
| D3 software | `- **No no-op deletions.** Ask: "Would deleting this word change any substantive obligation or right?" If not, leave it.` |
| P1 | `- **Edit in place.** Don't delete a sentence and then re-insert language from it as a tracked addition. Make the change inside the existing sentence.` |
| P2 | `- **Preserve structure.** Defined terms, numbering, indentation, and internal cross-references should still line up after your edits.` |
| P3 | ``- **Whole-section removal uses `mark_reserved.py`.** This keeps downstream numbering intact.`` |
| P4 | `- **Never propose a change in a comment alone.** Always make the change as a tracked edit; the comment explains *why*.` |

The model-visible task brief is `tasks/<id>/instruction.md`. `task.toml` has no system prompt. The image contains `/app/contract.docx`, `/app/grounding/*`, and `/skills/contract-redliner/`. Verifier files under `tests/` are not mounted. Dataset and GitHub READMEs, `docs/*`, and `eval.yaml` are not in the sandbox.

Harbor product system prompts (claude-code, codex, and similar) were not inspectable. They sit outside this repository. Condition text is not moved into those prompts.

Answer keys were not used to write the replacements.

## Where the brief is shared

140 `instruction.md` files. 12 unique texts, one per scenario and turn. Variants inside a scenario-turn are byte-identical. The hygiene block text is identical in all 140 files.

- Class A, heading at line 65 (64 files): AgentCo side. `redline-s1-t1-*`, `redline-s1-t3-*`, `redline-s2-t2-*`, `redline-s2-t4-*`, `redline-s3-t1-*`, `redline-s3-t3-*`.
- Class B, heading at line 66 (76 files): LargeCo or GiantCo side. `redline-s1-t2-*`, `redline-s1-t4-*`, `redline-s2-t1-*`, `redline-s2-t3-*`, `redline-s3-t2-*`, `redline-s3-t4-*`.

Class B line numbers for this block are class A plus 1. The transform does not use line numbers. It matches the exact strings, so both layouts take the same edit.

## Why D1–D3 are the generic-strategy set

These three lines are generic edit-shape coaching. They do not name a party, a deal term, a playbook position, a tool, or a document-format rule. They are the only spans designated for replacement or deletion.

- D1 is a quality pose for the edit itself (senior work product rather than a bot). It names no party, clause, tool, or output schema.
- D2 is a generic minimal-change rule plus a generic cost of extra visible markup. It does not say which provisions to change.
- D3 is a generic word-level stopping rule. The question already asks whether deleting the word would change a substantive obligation or right. The software sentence keeps that question and only renames the label "micro-deletions" to "no-op deletions".

The software sentences do not add patch, dependency, reference, preserve-behavior, a checklist, or a new test.

## Why P1–P4 stay

P1–P4 sit in the same hygiene section and stay, byte for byte, in all four conditions. They are document format, tool use, or delivery, not optional strategy.

- P1 fixes the shape of a Word tracked change: do not delete a sentence and reinsert retained words. Edit inside the existing sentence.
- P2 is a document-structure rule for defined terms, numbering, indentation, and internal cross-references. It stays even though it says "preserve".
- P3 is the tool-operation instruction for whole-section removal via `mark_reserved.py`.
- P4 is a delivery rule: a comment does not substitute for a tracked edit. The comment explains why.

After TASK_ONLY, the heading remains and these four bullets are what is left of the section.

## Why residual coaching stays

Other passages coach editing or negotiation, but each one is fused to a party position, a turn action, an output-voice rule, or a grounding file. Deleting or software-rewriting them would drop task substance, not only generic strategy. All four conditions keep them.

- R1, the representation voice tag, names walk-away subjects and deal posture. The comment-voice clause inside that tag stays because it is inside the party block.
- R2, the plan-in-tiers lists (base Process, turn-1 "How to plan", and response-turn "How to plan"), state priority for named issues or for accept/reject actions. "Be sparing" is welded to that list.
- R3, two turn-1 "what to do" sentences, restate targeted edits and the cost of visible red, but they are the turn's job: change substantive rights, and leave acceptable base language alone.
- R4, the response-turn addendum, is the turn's operational actions: four buckets, do not revert this side's prior edits, do not reopen mutually edited language, and limit brand-new issues. "Late-turn redlines lose credibility" is the rationale for that limit.
- R5, the "push back the right way" bullet, is a negotiation tactic inside the required comment-voice spec. The surrounding comment-discipline section, forbidden phrases, and worked example stay.
- R6, the scenario-3 must-win objective in the AgentCo context grounding file, is a commercial objective for that deal, including avoiding redlines that would jeopardize it.
- R7, the residual leak below, is grounding and stays byte for byte.

Also left unchanged: representation and hard constraints, negotiation posture, the base-mechanics pointer, "what you're looking at", turn-1 prohibitions, grounding path lists, session specifics, commercial playbooks and precedent contracts, `SKILL.md` and anchor guidance, script docstrings, the script-surface and anchor-failure sections, and Process steps other than the tier list. `tasks/*/task.toml` and the Dockerfiles carry no edit-strategy prose. The dataset README's `finalize()` mention is not a runtime instruction.

## Single insertion point

STOCK_PLUS_METAPHOR adds one sentence and nothing else, as its own paragraph, immediately after the blank line that follows `## Redlining hygiene` and before D1. It does not rewrite D1–D3. It is not written into `SKILL.md`, grounding, or a system prompt.

Result shape:

```text
## Redlining hygiene

Treat the agreement as an existing software system, its provisions as interacting components, and the requested revisions as patches to that system.

Edits should look like a senior lawyer's work product, not a redline-bot's:
```

Class A: the new paragraph is at line 67, and the current lead-in stays after it. Representative: `tasks/redline-s1-t1-g01a/instruction.md`, between lines 65 and 67. Class B: the new paragraph is at line 68. Representative: `tasks/redline-s1-t2-g01a/instruction.md`, between lines 66 and 68.

MATCHED_SOFTWARE_REPLACEMENT and TASK_ONLY do not receive this sentence.

## Four dispositions

| Span | STOCK | STOCK_PLUS_METAPHOR | MATCHED_SOFTWARE_REPLACEMENT | TASK_ONLY |
| --- | --- | --- | --- | --- |
| D1 lead-in | original | original, with the metaphor paragraph in the blank line above it | engineer / rewrite-bot sentence | delete the line and its newline |
| D2 targeted and minimal | original | original | other-party / large-diff sentence, same length | delete the line and its newline |
| D3 no micro-deletions | original | original | no-op deletions label, question unchanged, same length | delete the line and its newline |
| Metaphor sentence | absent | one insertion, hygiene section only | absent | absent |
| Heading, P1–P4, residual coaching, rejected paths | unchanged | unchanged | unchanged | unchanged |

STOCK still requires the heading, D1–D3, and P1–P4 each exactly once, then returns the text unchanged. Any other condition name, or a missing or duplicate span, raises `TransformError`. Edits are exact string operations. There is no wildcard replacement.

## Length deltas

| Span | Original characters | Software characters | Delta |
| --- | ---: | ---: | ---: |
| D1 | 75 | 77 | +2 |
| D2 | 152 | 152 | 0 |
| D3 | 119 | 119 | 0 |
| Metaphor sentence | 148 | inserted only by STOCK_PLUS_METAPHOR | — |

Document deltas on a brief that already has the stock hygiene block:

| Condition | Character delta | What changes |
| --- | ---: | --- |
| STOCK | 0 | Byte-identical. |
| STOCK_PLUS_METAPHOR | +150 | 148 characters of the sentence, plus the newline that ends it, plus the blank line that separates it from D1. |
| MATCHED_SOFTWARE_REPLACEMENT | +2 | D1 grows by 2. D2 and D3 stay the same length. |
| TASK_ONLY | −349 | Deletes the three lines and their newlines: 75 + 152 + 119 + 3. |

Same character length is not a semantic match. D2 and D3 were written to the same length as the originals. D1 is two characters longer. Whether the software sentences carry the same instruction is a judgment, reported by `length_report` and not measured by the tests.

## Residual leak

`Contract_Review_Guidelines_for_Reviewing_Attorneys_v1.extracted.md` is scenario-1 AgentCo grounding (`tasks/redline-s1-t1-g01a/...` and scenario-1 turn 3; not present for LargeCo, GiantCo, scenario 2, or scenario 3).

That file repeats D2 and D3 in different sentences and is intentionally not edited. Around the "Targeted, Minimal Edits" section it restates surgical, only-what-is-necessary edits and that counterparties react poorly to a lot of red. It also repeats the D3 question verbatim: `Ask: "Would deleting this word change any substantive obligation or right?" If not, leave it.` The exact D1–D3 bullets from `instruction.md` are not the lines in this file. The file also restates edit-in-place, reserved-section handling, formatting alignment, and "do not only propose a change in a comment", then continues into comment voice and cover-note format.

All four conditions keep this grounding file byte for byte. Deleting the overlapping lines would make TASK_ONLY asymmetric: only scenario-1 AgentCo tasks would lose the duplicate. After TASK_ONLY strips D2 and D3 from `instruction.md`, those tasks still see this coaching in grounding. That is the main residual leak, and it applies only to scenario-1 AgentCo turns.
