# Isolated local model evaluation

This directory is an offline model laboratory for parts 3 and 4. It does not change the
application runtime or publish influence links. The generated [evaluation.json](evaluation.json)
records actual runs on 3 October 2026. Public raw texts, vectors and model weights remain
under ignored `data/` or the Hugging Face cache.

## What the measurements say

All recall numbers use the same 172 LobbyPlag volunteer-verified pairs. Unlabelled
proposals remain retrieval distractors; they are not labelled negative examples.

| Corpus | BM25 | Qwen dense | Qwen + BM25 RRF | E5 dense | E5 + BM25 RRF |
| --- | ---: | ---: | ---: | ---: | ---: |
| New wording only, 1,159 proposal IDs | 129/172 | 115/172 | 130/172 | 111/172 | 130/172 |
| New wording or deleted wording, 1,158 nonempty proposals | **157/172** | 142/172 | 156/172 | 138/172 | 157/172 |

The corrected corpus reuses `_passage_text` and `_build_index` from the merged
`influence.practice.recall` implementation. One proposal has neither new nor deleted
text and is explicitly excluded. Recall still counts every one of the 172 positive pairs.
RRF is reciprocal rank fusion: each of the top 20 BM25 and dense results contributes
`1 / (60 + rank)`; the fused top 20 is evaluated.

**Retain deletion-preserving BM25.** Neither dense encoder improves recall. Qwen wins the
predeclared dense-model comparison, but its fusion loses one pair relative to BM25;
E5 fusion ties BM25. These are model-selection measurements on one historical,
lexically selected GDPR dataset, not independent validation or multilingual accuracy.

Qwen encoded 1,433 initial inputs in 29.70 seconds and the corrected 1,607-input corpus
in 31.33 seconds. E5 encoded the initial inputs in 3.70 seconds and the 174 additional
inputs in 0.64 seconds, reusing 1,433 validated cached vectors. These are inference times
on Apple M5 / 24 GB / MPS, batch size 8; downloads, loading and JSON output are separate.
Both encoders used a 512-token limit. Truncation counts and input keys are recorded in
artifacts; no claim is made that truncated long inputs were fully represented.

The local NLI judge scored 272 public practice pairs plus 24 predeclared synthetic legal
cases in 11.89 seconds. It matched only **17/24** intended synthetic relations. Failures
include scope, thresholds, permission versus obligation, and same-topic changes. Synthetic
labels are separate from raw outputs and require independent legal review. LobbyPlag copy
labels are **not** entailment labels. These scores are development features, not permission
to publish semantic links. The parent grouped evaluator measures their effect separately.

## Models and runtime

| Model | Frozen revision | Model-card source |
| --- | --- | --- |
| Qwen3-Embedding-0.6B | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | [Qwen model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/tree/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3) |
| multilingual-e5-small | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) |
| nli-deberta-v3-small | `fa2804872c3b4bd748f38c0185cc85775361e735` | [Cross-Encoder model card](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735) |

`pyproject.toml` and the generated `uv.lock` isolate Python 3.14, PyTorch, Transformers,
safetensors, NumPy and Hugging Face Hub from the lightweight backend. Pytest is a development
dependency for four offline tests. Direct versions are exact; `exclude-newer = "14 days"`
and `no-build = true` apply to resolution, and installation is locked. Models use
`trust_remote_code=False`, `use_safetensors=True`, and inference loads only local frozen
files. The download helper admits tokenizer/configuration files and safe tensors, not
Python code or pickle weights. No paid provider API is used.

Qwen uses the model card's last-token pooling with left padding and a retrieval instruction;
E5 uses masked-mean pooling with `query:` / `passage:` prefixes. Both normalize in float32
after float16 MPS inference. NLI uses float32 and checks the model's explicit class mapping.
PyTorch emitted a Python 3.14 TorchScript deprecation warning during DeBERTa loading; the
recorded inference completed with finite outputs. This is retained as a runtime limitation.

## Reproduce from the repository root

Use a checkout whose main backend includes `influence.practice.recall`. Replace the public
LobbyPlag directory with the directory of your downloaded dataset.

```sh
uv sync --project backend/models --locked
uv run --directory backend --locked python models/prepare_lobbyplag.py \
  --data /absolute/path/to/data/lobbyplag --out ../data/semantic-evaluation
uv run --project backend/models --locked python backend/models/download.py qwen
uv run --project backend/models --locked python backend/models/embed.py \
  --model qwen --inputs data/semantic-evaluation/inputs.json \
  --labels data/semantic-evaluation/labels.json --out data/semantic-evaluation/qwen
uv run --project backend/models --locked python backend/models/download.py e5
uv run --project backend/models --locked python backend/models/embed.py \
  --model e5 --inputs data/semantic-evaluation/inputs.json \
  --labels data/semantic-evaluation/labels.json --out data/semantic-evaluation/e5
uv run --project backend/models --locked python backend/models/download.py judge
uv run --project backend/models --locked python backend/models/judge.py \
  --inputs data/semantic-evaluation/inputs.json --out data/semantic-evaluation/judge
```

Only one heavyweight model is run at a time. `embed.py --device cpu` is available but was
not benchmarked here. `--reuse-embeddings PATH` accepts only matching model revision,
instruction, pooling, dtype, token limit, source hashes, vector dimensions and normalization.
It reuses content-and-role identities already present; legacy caches without this provenance
are rejected. The original new-text experiment remains recorded in `evaluation.json`; the
current preparation command intentionally reproduces the corrected deletion-preserving corpus.

Verification commands:

```sh
uv run --directory backend --locked ruff check models
uv run --directory backend --locked ruff format --check models
uv run --directory backend --locked basedpyright --project models --pythonpath models/.venv/bin/python
uv run --directory backend/models --locked pytest
uv audit --directory backend/models --locked --preview-features audit-command
```

Measured: four tests passed, Ruff checks passed, isolated audit reported no known
vulnerabilities. The command above checks every isolated script and test in strict mode
with warnings treated as failures. Both locked environments must first be installed:
`extraPaths` resolves the preparation script's main-pipeline imports and its Pydantic
dependency, while `--pythonpath` supplies the isolated Torch/Transformers environment.
Narrow line-level exceptions cover only incomplete third-party annotations (dynamic
model factories, Torch tensor `tolist`, seed typing, Hub optional overload parameters)
and intentional reuse of the pipeline's private recall corpus helpers. Model factories
are narrowed to their installed base-class interfaces; tensor conversions have explicit
shape-derived element types. No module-wide typing diagnostics are disabled.

## Artifact contract and handoff

The run creates `inputs.json` and a **separate** `labels.json`. Text identity is
`sha256((role + "\0" + raw_text).encode("utf-8"))`; role is `query` or `passage`.
Pair semantic text is the existing `changed_spans` token diff, each exact span prefixed
`INSERT: ` or `DELETE: ` and joined with newlines. Unchanged boilerplate is excluded.
The retrieval query is that tagged amendment delta; the retrieval corpus uses complete
new wording, or old wording for deletion-only proposals. Full-new-text diagnostic keys
are also retained for the NLI experiment.

- `embeddings.json`: frozen model/run metadata and a key-to-normalized-vector mapping.
- `semantic-pairs.json`: schema `semantic-pairs-1`, model and source provenance, and
  `pairs` with candidate/amendment/proposal IDs, delta/full-text keys and `cosine`.
  A no-change side produces `cosine: null` and an explicit `missing_reason`, never zero.
- `retrieval-report.json`: BM25, dense and fused recall with per-positive hit flags.
- `judge-pairs.json`: schema `local-nli-pairs-1`; each pair has `candidate_id`,
  `premise_sha256`, `hypothesis_sha256`, raw `contradiction`, `entailment`, `neutral`,
  and `predicted`. It binds full new amendment text as premise and full new proposal
  text as hypothesis; it does not decide publication. This is a full-new-text NLI
  diagnostic, not the plan’s change-conditioned judge and not a generative judge that
  returns source quotes. Those remain unimplemented experiments; shared boilerplate
  and the measured diagnostic failures prevent activating this baseline.
- `judge-diagnostic-output.json` contains raw synthetic predictions, while
  `judge-diagnostic-report.json` joins the separately stored intended labels afterward.

Actual artifacts in this session are under
`/Users/lensa/Projects/reversa-madrid-open/data/semantic-evaluation/`. Corrected retrieval
inputs and model artifacts are in its `deletions/` directory; the judge artifacts are in
`judge/` and bind the initial root `inputs.json`. Neither raw data nor vectors are committed.
