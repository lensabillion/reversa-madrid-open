# Practice Harness

The practice harness is the architecture's **practice loop**: it checks part 4's scores the
way the hidden test will, before a change reaches `pairs.csv`. It labels LobbyPlag's public
GDPR candidates, splits them into folds, scores every pair out of fold, and measures each
scorer on 2,000 simulated hidden tests of 30 real pairs and 30 decoys. Every scorer change
reports these numbers before and after, on the same folds and seeds (`AGENTS.md`, "Model
changes are accepted on evaluation evidence").

```sh
uv run --directory backend --locked python -m influence.practice \
    --data /absolute/path/to/data/lobbyplag --out evaluation/practice-results.json
```

`practice-results.json` is generated: the input files' SHA-256 digests, the label counts and
rules, the folds, the settings and every pair's score. It records no paths or timings, so
a rerun on the same snapshot reproduces it byte for byte.

| Scorer | Precision in top 20 (p10) | Recall at 0.5 (p10) | AUC (p10) |
| --- | ---: | ---: | ---: |
| Lexical comparison on `main` (`lexical-delta-v1`) | 0.980 (0.950) | 0.814 (0.733) | 0.863 (0.802) |
| LobbyPlag's stored match score (sanity baseline) | 0.857 (0.750) | 1.000 (1.000) | 0.810 (0.748) |

Means over the 2,000 tests; p10 is the 10th percentile, the score of a bad draw. The
stored match reproduces the explainer's 0.86 and 0.81. Its recall is 1.0 only because it
never scores a candidate below 0.5; it exists only for pairs LobbyPlag's matcher proposed,
so it cannot score the hidden test.

**Labels.** Positive: a volunteer verified the copy (172 pairs). Weak negative: crowd
volunteers checked the pair and none voted it a copy (100 pairs; 95 rest on one check).
They are weaker than the positives (review finding R1). The other 1,685 candidates are
unlabelled and excluded; no negative is invented (R2). No identical inputs carry opposite
labels. A run takes 0.27 s on an Apple M5.

**Folds.** No organization, amendment text or submission text appears on both sides of a
split (R4). One linked group holds 10 organizations, 214 amendments and 170 of the 172
positives, so the five folds are organizations, and training pairs sharing a text with the
test fold are withheld from its training (8 to 23 per fold).

**Read with care.** One law, in English, mostly word-for-word copies; the 2,000 tests reuse
the same 272 pairs, so they are not independent samples. The per-fold numbers show where
the lexical scorer is weak:

| Fold | Organizations | Positives | Lexical AUC | Lexical recall |
| ---: | --- | ---: | ---: | ---: |
| 0 | edri, ekd-dbk, microsoft | 79 | 0.987 | 0.962 |
| 1 | agoria, bitkom, bof, euroispa | 23 | 0.682 | 0.609 |
| 2 | amcham, ebay | 24 | 0.655 | 0.542 |
| 3 | amazon, eurofinas, telefonica | 23 | 0.969 | 0.957 |
| 4 | accis, cocir, digitaleurope, ebf | 23 | 0.737 | 0.652 |

Fold 0 is mostly European Digital Rights' near-verbatim copies. Where organizations' wording
was adapted rather than copied, shared changed words alone separate real pairs from
decoys much less well; that is what the passage finder and the next signals must improve.

# Frozen semantic-agreement diagnostic

The current lexical scorer prefers the intended match in **2 of 10 synthetic triplets**.
One frozen Qwen reranker experiment prefers it in **8 of 10**. This is a useful signal
for further work, **not measured influence accuracy**, a production replacement, or a
calibrated probability. Production scoring and API behavior are unchanged.

## What was measured

`diagnostics.json` contains ten agent-authored examples, each with an amendment, a
preferred submission, and a decoy. “Preferred” means the closer requested legal outcome
in that illustrative example; it does not assert historical borrowing. The examples
cover paraphrases, contrary requests, quantities, common wording, shared deletions,
negation scope, legal obligations, literal equality, and unchanged law. No hidden test
inputs were used. These are designed failure probes, not a representative random sample.

The fixture was frozen before model inference, SHA-256
`9723ea195124bb81a78df8e5cb69a3d347557bfc4243d7bdbf7230b8368d800a`.
No model training, prompt search, threshold tuning, score blending, or fixture revision
followed the results. The model receives only each pair's wording, not its label or
category. One task instruction compares requested legal outcomes, while preserving
known originals and explicitly marking unknown originals. The exact prompt is retained
in `qwen-results.json` and in [`runtime/run_qwen.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/backend/evaluation/runtime/run_qwen.py).

| Case | Lexical preferred / decoy | Qwen preferred / decoy | Preferred ranked first: lexical / Qwen |
| --- | --- | --- | --- |
| Paraphrase | 0.000 / 0.067 | 0.983 / 0.253 | No / Yes |
| Permit versus prohibit | 0.214 / 0.727 | 0.886 / 0.070 | No / Yes |
| 24 versus 72 hours | 0.313 / 0.769 | 0.766 / 0.838 | No / No |
| 2% versus 20% | 0.150 / 0.842 | 0.993 / 0.987 | No / Yes |
| Shared boilerplate | 0.045 / 0.889 | 0.985 / 0.315 | No / Yes |
| Shared deletion | 0.753 / 0.914 | 0.986 / 0.892 | No / Yes |
| Negation scope | 0.000 / 0.700 | 0.938 / 0.910 | No / Yes |
| Mandatory versus permitted | 0.385 / 0.727 | 0.967 / 0.995 | No / No |
| Literal control | 1.000 / 0.077 | 0.995 / 0.196 | Yes / Yes |
| Unchanged-law control | 1.000 / 0.000 | 0.993 / 0.929 | Yes / Yes |

Each metric is one strict `preferred_score > decoy_score` comparison. Ties count
separately; neither run had a tie. These ten comparisons are not precision@20, recall
on 30 real pairs, AUC, or evidence of generalization. Numeric score scales differ.
Qwen's score normalizes the next-token “yes” and “no” logits, following its model card;
that transformation does not calibrate it to influence.

The remaining failures are material. A conflicting deadline and a weaker obligation
rank above the intended match. Several other decoys score above 0.89, including one
with no change at all. Even the correctly ordered percentage example has a tiny margin.
A threshold of 0.5 would not make these scores reliable decisions. The model is a
[relevance reranker](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B), not a model trained
to establish who influenced legislation.

## Reproduce

Run the lexical diagnostic from the repository root, with uv and Python 3.14:

```sh
uv run --directory backend --locked python tests/diagnostics_lexical.py
```

It prints deterministic JSON; `lexical-results.json` records this run.

The Qwen runtime was removed from the tree on 3 October 2026: nothing in the pipeline
uses it, and its 55-package lock was audited over the network on every `make check`.
Its code, lock and `make` targets remain in git history at commit
[`1142700`](https://github.com/lensabillion/reversa-madrid-open/tree/114270050273783490dba8c7527bd9d9e270fd7e/backend/evaluation/runtime). To rerun it, check out that commit and run
`make check-evaluation-runtime`, then
`uv run --directory backend/evaluation/runtime --locked python run_qwen.py`.
The semantic command downloads only the pinned model's JSON/text/safetensors files
under ignored `data/models/`, verifies its weights, then atomically replaces
`qwen-results.json` after all 20 scores succeed. It rejects a changed fixture, a weight
checksum mismatch, inputs above 2,048 model tokens, and nonfinite outputs; it never
silently truncates, invokes remote model code, calls a paid API, or generates labels.
Network/setup/model exceptions fail the run. The optional heavyweight command is an
experiment, not an online endpoint or hardened untrusted-input service. Keep the
published result file if retaining the first timing measurement matters.

The isolated runtime had its own generated `uv.lock`, separate from production:

- Python 3.14.7; `torch==2.14.0`, official arm64 cp314 wheel published 2026-09-02.
- `transformers==5.17.0`, universal wheel published 2026-09-09.
- All transitive releases resolved before the fixed cutoff 2026-09-18T00:00:00Z;
  source builds disabled. No age exception was used.
- Official model `Qwen/Qwen3-Reranker-0.6B`, revision
  `e61197ed45024b0ed8a2d74b80b4d909f1255473`, Apache-2.0 model license.
- Weights: 1,191,588,280 bytes; SHA-256
  `27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b`.
- Seed 0, CPU float32, four PyTorch threads, evaluation/inference modes; no sampling.
  Third-party missing annotations have narrow documented type-check suppressions.

The first run on Apple M5 (10 CPU cores, 24 GiB RAM), macOS 26.6.2, measured 17.47 s
for download, 0.79 s for model loading, and **3.97 s for 20 scored pairs**. The largest
prompt was 217 model tokens. Startup/import/checksum time is outside those measurements.
These short inputs do not establish throughput for long documents or a complete 60-pair,
20-proposal pipeline. Attention has quadratic sequence-length cost; 2,048 is a protective
experiment limit, not evidence that all such inputs meet the short-case timing.

Validation at the time of the run: runtime Ruff and strict basedpyright passed, and the
isolated dependency audit reported “Found no known vulnerabilities and no adverse project
statuses in 54 packages”. The default unit tests validate the lexical diagnostic
loader/ordering contracts without requiring model downloads; actual semantic inference
was the explicit outer-tier check. Since the runtime's removal, `make check` and backend
CI audit only `backend/uv.lock`.
The model itself has not been unit-tested for arbitrary legal correctness.

## Public labels and next decision

The available public LobbyPlag snapshot has 1,976 raw candidate rows, 1,957 unique
candidate IDs, 172 unique verified links, and 172 checked links (zero checked-but-unverified).
Source: local public `data/lobbyplag/plags.json`, SHA-256
`fb21f05cc0c372fdc60a2117219262cb7b00d52196ebbb118b29fc786dfb9a3c`.
Unverified rows have no
trusted negative label. (The practice harness above uses a different field: 100 candidates
have crowd checks in `processing.checked` and no yes vote, which it treats as weak
negatives and labels as such.) Consequently this experiment cannot report real-world precision,
calibration, or influence AUC from that snapshot. No candidate was converted to a
negative merely because it was unverified.

Before promoting a scorer, obtain independently justified public negatives, freeze a
held-out evaluation split grouped by organization and overlapping/duplicate amendment
passages, and evaluate the same examples with both scorers. Measure passage retrieval
recall separately when submissions are long. A new model must improve held-out top-20
precision without materially reducing the organizer-defined recall, while reporting
uncertainty from the small number of independent groups. Resolve the organizer's recall
threshold definition before choosing a decision threshold. Preserve quoted evidence
and original offsets; relevance logits alone provide neither.

For this candidate, quantities, obligation strength, and unchanged-law rejection need
further independent diagnostics and domain evidence before any production adoption.
An additional prompt chosen after inspecting these ten cases would be development,
not a new held-out result. Adoption of proposals into final law remains a separate
prediction target and is not implemented or assessed here.
