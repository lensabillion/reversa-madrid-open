# Open Models for The Influence Atlas: a Hugging Face Shortlist

Researched Saturday 3 October 2026 for Reversa Challenge 03 (Madrid Open). No weights were downloaded and nothing in
the repository was changed.

**How to read the tags.**
- `verified`: read today from the Hugging Face model or dataset API (`/api/models/<id>?blobs=true`,
  `/commits/main`), the raw `README.md` of the card, the PyPI JSON API, or a file in this repository.
- `reported`: taken from a third-party page, from a model card's own claims about its training data, or from general
  knowledge I could not confirm today.
- `guess`: my own estimate, with the arithmetic shown.

Sizes are the sum of the repository's weight files: safetensors if there are any, otherwise `.bin`/`.pt`. The 14-day
cut-off for the supply-chain rule is **2026-09-19**.

---

## 1. Summary table

| Role | First choice | Fallback | Licence (card) | Weights on disk | Why |
| --- | --- | --- | --- | --- | --- |
| Dense multilingual retrieval | `Qwen/Qwen3-Embedding-0.6B` | `ibm-granite/granite-embedding-311m-multilingual-r2` (faster); `BAAI/bge-m3` (adds sparse retrieval) | Apache-2.0 / Apache-2.0 / MIT | 1.19 GB / 0.62 GB / 2.27 GB (bge-m3 ships `.bin` only) | Best open MMTEB score under 1B (64.33 mean, 64.64 retrieval). It takes instructions, has a 32k context and needs no remote code. Same backbone as the reranker you already ran |
| Cross-encoder reranking | `Qwen/Qwen3-Reranker-0.6B` @ `e61197ed…` (the revision you measured) | `BAAI/bge-reranker-v2-m3`; `mixedbread-ai/mxbai-rerank-base-v2` | Apache-2.0 / Apache-2.0 / Apache-2.0 | 1.19 / 2.27 / 0.99 GB | MMTEB-R 66.36 vs 58.36 for bge-reranker-v2-m3. Already 8/10 on your triplets |
| Direction check: same request vs opposite request (NLI) | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` (English only, stronger) | MIT / MIT | 0.56 / 0.87 GB | Gives a contradiction probability, which a reranker cannot. It covers 100 languages, with XNLI accuracy 0.74–0.87 |
| Local LLM judge and extractor (JSON) | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `ibm-granite/granite-4.2-8b-q4-mlx`; `mlx-community/Ministral-3-8B-Instruct-2512-4bit` | Apache-2.0 (all three) | 2.26 / 4.95 / 5.60 GB | Non-thinking only, 262k context, fits easily in 24 GB. Granite has an official IBM MLX build |
| EU topic classification | Use the EuroVoc descriptors EUR-Lex already attaches to each act (no model needed) | `EuropeanParliament/EuroVoc` classifier; zero-shot with the NLI model above | EUPL-1.2 | 1.23 GB (multilingual) / 0.46 GB (older, English) | An official multilingual EuroVoc tagger exists, but its multilingual revision is **11 days old** |
| Translation | Not needed for matching (use multilingual embeddings). For display, use `Helsinki-NLP/opus-mt-<src>-en` per language pair | `facebook/m2m100_418M`; `google/madlad400-3b-mt` | Apache-2.0 (HF metadata) / MIT / Apache-2.0 | 0.30 / 1.94 (.bin) / 11.8 GB | NLLB-200 is CC-BY-NC: exclude it |
| PDF parsing | `pypdf` (already pinned) or `pypdfium2`; `docling` only for the PDFs that fail | `docling` with `docling-project/docling-layout-heron` | BSD-3 / BSD-3+Apache / MIT + Apache | 0.17 GB layout model | Docling has Python 3.14 wheels. Avoid PyMuPDF (AGPL), marker/surya weights (OpenRAIL) and nougat (NC) |
| Organisation NER | `urchade/gliner_multi-v2.1` | `fastino/gliner2-multi-v1`; `Davlan/xlm-roberta-base-ner-hrl` | Apache-2.0 / Apache-2.0 / AFL-3.0 | 1.16 / 1.23 / 1.11 GB | Zero-shot labels ("organisation", "trade association"), multilingual |
| Entity matching | `rapidfuzz` plus the embedding model above | – | MIT | – | Prefer exact Transparency Register IDs whenever a source has them |
| Stance and claim comparison | The LLM judge (claim extraction to JSON) plus the NLI model (entail or contradict) | ClimateBERT, for climate only | Apache-2.0 weights, but trained on CC-BY-NC-SA data | 0.33 GB | No policy-stance model fits this task |

---

## 2. Per-role details

### 2.1 Multilingual dense embeddings (retrieval)

| Repo id | Params | Weights | Licence | Context | Languages | Created / last modified | Benchmarks | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3-Embedding-0.6B` | 595.8M | 1.19 GB bf16 safetensors | apache-2.0 | 32k (card); card example uses `max_length=8192` | 100+ | 2025-06-03 / 2026-04-20 | MTEB Multilingual mean (task) **64.33**, Retrieval **64.64**, Pair classification 80.83, STS 76.17 | Takes instructions; the card says leaving out a query instruction costs 1–5% retrieval. No remote code. MLX ports exist (`mlx-community/Qwen3-Embedding-0.6B-8bit`, 0.63 GB). Sha `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| `Qwen/Qwen3-Embedding-4B` | 4.02B | 8.04 GB | apache-2.0 | 32k | 100+ | 2025-06-03 / 2025-06-20 | MMTEB mean 69.45, Retrieval 69.60 | Too slow for 540k amendments on a laptop. Possible for re-embedding the top candidates only |
| `ibm-granite/granite-embedding-311m-multilingual-r2` | 311.7M | 0.62 GB | apache-2.0 | 32,768 | 200+ pretrained, 52 with enhanced support | 2026-04-20 / 2026-05-18 | "MTEB ML Retrieval (18)" **65.2**, LongEmbed 71.7, 1,828 docs/s on H100 (card) | ModernBERT, no remote code, Matryoshka down to 128 dimensions. Its 18-task retrieval subset is not the same as Qwen's MMTEB column, so the two scores are not directly comparable. Sha `44399559930365213510b1ee2eb15ded83374f0e` |
| `ibm-granite/granite-embedding-97m-multilingual-r2` | 97.4M | 0.20 GB | apache-2.0 | 32,768 | as above | 2026-04-20 / 2026-05-18 | ML Retrieval 60.3 (card table) | The option for embedding the whole corpus of about 540k amendments |
| `BAAI/bge-m3` | ~568M (XLM-R large) | 2.27 GB **`.bin` only**, no safetensors; ONNX 2.27 GB | mit | 8192 | 100+ | 2024-01-27 / 2024-07-03 | MMTEB mean 59.56, Retrieval 54.60 (as reported in the Qwen card's table) | Gives dense, sparse and ColBERT vectors in one model, which suits hybrid lexical-plus-dense retrieval. `.bin` is a pickle, so it fails under `use_safetensors=True`. `mlx-community/bge-m3-mlx-fp16` (1.14 GB) has safetensors |
| `intfloat/multilingual-e5-large-instruct` | 559.9M | 1.12 GB | mit | 512 | ~94 | 2024-02-08 / 2025-07-10 | MMTEB mean 63.22, Retrieval 57.12 (Qwen card table) | The 512-token limit cuts long submission passages |
| `Snowflake/snowflake-arctic-embed-l-v2.0` | 567.8M | 2.27 GB | apache-2.0 | 8192 | 74 | 2024-11-08 / 2025-07-28 | MTEB numbers are in the card metadata; not extracted | No remote code |
| `Alibaba-NLP/gte-multilingual-base` | 305.4M | 0.61 GB | apache-2.0 | 8192 | 75 | 2024-07-20 / 2025-07-05 | – | **Needs `trust_remote_code`** (has an `auto_map`): it runs repository code on your machine |
| `nomic-ai/nomic-embed-text-v2-moe` | 475M | 1.90 GB | apache-2.0 | **512** | ~100 | 2025-02-07 / 2025-04-01 | – | Needs `trust_remote_code` |
| `google/embeddinggemma-300m` | 302.9M | 1.23 GB | gemma | – | – | 2025-07-17 / 2025-09-25 | – | **Gated** (manual approval): the card returned HTTP 401 without a login. Excluded for rerunnability |
| `jinaai/jina-embeddings-v3`, `jina-embeddings-v5-text-small`, `-nano` | 572M / 596M / 212M | – | **cc-by-nc-4.0** | – | – | – | – | **Excluded: non-commercial** |

**Legal-domain embeddings for EU law.** There is no maintained multilingual *sentence-embedding* model for EU law with
a clear permissive licence (verified by Hub searches for "legal-xlm", "legal-bert", "eurlex" and "eurovoc"). What
exists:
- `joelniklaus/legal-xlm-roberta-base` / `-large`: 184M / 435M parameters, 25 languages. These are fill-mask
  pretraining models, not embedders; they would need contrastive fine-tuning. The licence field is just `cc`, which is
  ambiguous.
- `nlpaueb/legal-bert-base-uncased` and `nlpaueb/bert-base-uncased-eurlex`: English only, cc-by-sa-4.0, `.bin` only,
  fill-mask.
- `Stern5497/sbert-legal-xlm-roberta-base`: a sentence-similarity model with **no licence declared**. Avoid it.

`mteb/eurlex-multilingual` (cc-by-sa-4.0) is an MTEB retrieval task. Its per-task leaderboard is the right place to
compare general models on EUR-Lex text; I did not read that leaderboard today.

**Throughput on Apple Silicon:**
- `verified` anchor from your repository: `backend/evaluation/qwen-results.json` shows Qwen3-Reranker-0.6B scoring 20
  pairs (up to 2,048 tokens each) in 3.97 s, on CPU, float32, 4 threads, torch 2.14.0, Python 3.14.7, macOS 26.6.2.
  That is about 5 pairs/s. A 0.6B embedder does the same forward pass per token.
- `guess`: on MPS in fp16 with passages of about 256 tokens, expect 50–150 passages/s for the 0.6B models and roughly
  3–5× that for granite-97m.

**Planning arithmetic (`guess`):**
- One law: about 2,000 amendments + 300 submissions × 30 passages ≈ 11k texts. That is about 2–4 minutes with
  Qwen3-Embedding-0.6B on MPS.
- All 540k amendments plus about 1M passages ≈ 1.5M texts. That is about 3–8 hours with the 0.6B model, or about 1–2
  hours with granite-97m.
- So embed the whole corpus offline with the small model, or use the 0.6B model only for the laws in the demo.

### 2.2 Cross-encoder rerankers

| Repo id | Params | Weights | Licence | Context | Created / modified | Benchmarks (Qwen card table, rerank top-100 from Qwen3-Embedding-0.6B) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3-Reranker-0.6B` | 595.8M | 1.19 GB | apache-2.0 | 32k | 2025-05-29 / 2026-04-16 | MTEB-R 65.80, **MMTEB-R 66.36**, MLDR 67.28 | HEAD `e61197ed45024b0ed8a2d74b80b4d909f1255473` is the revision in your `qwen-results.json` and is titled "Integrate with Sentence Transformers v5.4", so it loads as a `CrossEncoder`. MLX: `mlx-community/Qwen3-Reranker-0.6B-4bit` (created 2026-06-06) |
| `Qwen/Qwen3-Reranker-4B` | 4.02B | 8.04 GB | apache-2.0 | 32k | 2025-06-03 / 2026-04-16 | MMTEB-R 72.74 | Only for the final few hundred candidates |
| `BAAI/bge-reranker-v2-m3` | 567.8M | 2.27 GB safetensors | apache-2.0 | card examples use 512–1024 | 2024-03-15 / 2024-06-24 | MMTEB-R 58.36, MLDR 59.51 | Mature and no remote code |
| `mixedbread-ai/mxbai-rerank-base-v2` | 494M (Qwen2) | 0.99 GB | apache-2.0 | 32k max positions (config) | 2025-03-03 / 2026-04-08 | Own benchmark: BEIR 55.57, "Multilingual" 28.56, A100 latency 0.67 s | Card claims 100+ languages; its multilingual score is weak in its own table |
| `Alibaba-NLP/gte-multilingual-reranker-base` | 306M | 0.61 GB | apache-2.0 | 8192 | 2024-07-20 / 2025-07-05 | MMTEB-R 59.44 | **Remote code** |
| `jinaai/jina-reranker-v2-base-multilingual`, `jinaai/jina-reranker-v3` | 278M / 597M | – | **cc-by-nc-4.0** | – | – | MMTEB-R 63.73 (v2) | **Excluded** |
| `zeroentropy/zerank-2-reranker` | 4.02B | 8.05 GB | apache-2.0 (metadata) | – | 2025-11-19 / 2026-07-24 | – | Metadata lists one language; not checked further |

**Can a reranker be repurposed as a paraphrase or reuse judge?**
- Only partly. Qwen3-Reranker reads the logit for "yes" after a custom instruction, so you can ask "Does the
  Document request the same legal change as the Query?". That is `verified` from the card format and your
  repository's experiment.
- Your measurement shows it still rewards same-topic but opposite submissions (`verified`, repository).
- Treat the reranker score as a **recall and ordering** feature, and add a separate *direction* signal: NLI
  contradiction (section 2.3) plus the LLM verdict (section 2.4).

### 2.3 NLI and paraphrase identification

| Repo id | Params | Weights | Licence | Languages | Created / modified | Accuracy (card) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | 278.8M | 0.56 GB | mit | 100 pretrained, NLI fine-tuned on 27 | 2022-08-22 / 2024-04-11 | XNLI: en 0.871, de 0.824, fr 0.823, es 0.832, bg 0.822 (bg was not in its training set); MNLI-m 0.857; **ANLI 0.537** | Trained on machine-translated NLI (the card says this "reduces the quality"). Sha `b5113eb38ab63efdd7f280f8c144ea8b13f978ce` |
| `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` | 435M | 0.87 GB | mit | English | 2022-06-06 / 2024-04-11 | MNLI-m 0.912, ANLI 0.702, WANLI 0.77 | The strongest open English NLI model here. Usable when both sides are English or translated to English |
| `cross-encoder/nli-deberta-v3-large` / `-base` | 435M / 184M | 1.74 / 0.74 GB | apache-2.0 | English | – / 2025-04 | SNLI 92.20, MNLI-mm 90.49 (large) | Native `sentence-transformers` CrossEncoder |
| `MoritzLaurer/bge-m3-zeroshot-v2.0` | 568M | 1.14 GB | mit | multilingual (bge-m3 base, 8192 context) | 2024-04-02 / 2024-04-22 | Zero-shot mean 0.59 (`-c` variant) | Long-context multilingual zero-shot classifier. The card says variants without `-c` include training data under "a broader mix of licenses" |
| `joeddav/xlm-roberta-large-xnli` | 561M | 2.24 GB | mit | 15 XNLI languages | 2022 / 2024-10-16 | – | Older and large |
| `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli` | 107M | 0.43 GB | mit | 16 | 2023 / 2024-04-22 | – | Fast pre-filter |

- **PAWS-X paraphrase models.** The Hub has only single-language PAWS-X classifiers (Spanish, French and German
  BERT or ALBERT models from 2022, verified by search). None is multilingual or maintained, so skip them.
- **How to use NLI here (my recommendation).**
  1. Express the amendment's *change* as a hypothesis, for example "The text should require X".
  2. Use the lobby passage as the premise.
  3. Score both directions.
  4. Use P(contradiction) as a veto on the reranker score, and P(entailment) as a positive feature.
- DeBERTa-v3 is known to overflow in fp16 (`reported`), so run it in fp32 on CPU. At about 280M parameters it should
  manage roughly 20–60 pairs/s on 512-token pairs (`guess`).

### 2.4 Small instruction LLMs (judge and extractor, JSON output)

`mlx-lm` 0.31.3 (released 2026-04-22) contains `qwen3.py`, `qwen3_5.py`, `qwen3_moe.py`, `granite.py`,
`mistral3.py`, `ministral3.py`, `gemma4.py` and `gemma4_text.py` (verified on GitHub at tag `v0.31.3`).

| Repo id (MLX build) | Base | Params | 4-bit weights | Licence | Context | Created / modified | model_type | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `Qwen/Qwen3-4B-Instruct-2507` | 4.02B | **2.26 GB** | apache-2.0 | 262,144 | 2025-08-06 / 2026-01-02 | qwen3 | **Non-thinking only** (card), so no `<think>` tokens are spent. Sha `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b` |
| `mlx-community/Qwen3.5-4B-4bit` / `Qwen3.5-9B-4bit` | `Qwen/Qwen3.5-4B` / `9B` | 4.66B / 9.65B | 3.03 / 5.95 GB | apache-2.0 (base card; the 4B MLX repo declares no licence) | 262,144 | 2026-03-02 | qwen3_5 (vision-language) | 201 languages. **Thinks by default**: disable it in the chat template. The MLX card says to install `mlx-vlm` |
| `ibm-granite/granite-4.2-8b-q4-mlx` | `ibm-granite/granite-4.2-8b` | 8.79B | 4.95 GB | apache-2.0 | 128K native | 2026-09-01 / 2026-09-02 (31 days old) | granite | Official IBM MLX build. Thinking can be switched on or off. Tested in 12 languages, including de, es, fr, it, pt, nl and cs |
| `mlx-community/Ministral-3-8B-Instruct-2512-4bit` | `mistralai/Ministral-3-8B-Instruct-2512` | 8.9B | 5.60 GB | apache-2.0 | 256k | 2025-12-03 / 2025-12-06 | mistral3 | Strong in EU languages, per Mistral's card |
| `mlx-community/Ministral-3-14B-Instruct-2512-4bit` | 14B | 13.9B | 8.43 GB | apache-2.0 | 256k | 2025-12-03 | mistral3 | Slower; about 9 tok/s ceiling (`guess`) |
| `mlx-community/gemma-4-12B-it-qat-4bit` | `google/gemma-4-12B-it` | 12.0B | 10.99 GB | base card **apache-2.0**; MLX repo declares none | 256K | 2026-06-05 | `gemma4_unified`, not in mlx-lm 0.31.3, so it needs `mlx-vlm` | Gemma 4 is Apache-2.0 per its card metadata. **Gemma 3 is still under the `gemma` terms and gated** |
| `mlx-community/phi-4-4bit` / `Phi-4-mini-instruct-4bit` | `microsoft/phi-4` / `Phi-4-mini-instruct` | 14.7B / 3.8B | 8.25 / 2.16 GB | mit | 16K (phi-4) | 2024-12 / 2025-02 | – | The phi-4 card says it is "trained primarily on English text": a poor fit for multilingual submissions |
| `mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit` | 30.5B MoE | 30.5B (3B active) | **17.18 GB** | apache-2.0 | 262,144 | 2025-07-29 | qwen3_moe | **Does not fit comfortably in 24 GB** (see section 4) |
| `mlx-community/Qwen3.6-35B-A3B-4bit` | 35.1B MoE | – | 20.40 GB | apache-2.0 | – | 2026-04-16 | – | Too big |
| `utter-project/EuroLLM-9B-Instruct` | – | 9.15B | 18.3 GB bf16 | apache-2.0 | – | 2024-11-22 | – | **Gated ("auto")**: users must log in and accept terms, which hurts rerunnability. 35 languages |

`Qwen/Qwen3.8-27B` (apache-2.0, released 2026-08-05) is too slow on 24 GB. `Qwen/Qwen3.8-Flash-Next` has 180B
parameters and licence `other`.

**Throughput.**
- `reported` (Apple ML Research page): the base M5 with 24 GB has **153 GB/s** memory bandwidth (M4: 120 GB/s).
  Apple measured generation 1.19–1.27× faster than the M4 and time-to-first-token 3.3–4.1× faster, with mlx-lm on
  4-bit Qwen 8B, 14B and 30B-A3B.
- `reported` (awni gist): Qwen3-30B-A3B-Instruct-2507-4bit generates 113 tok/s on an M4 Max, which has about 3.5× the
  bandwidth of an M5.
- `guess`: generation speed is roughly bandwidth ÷ weight bytes, at about 70% efficiency.

| Model (4-bit) | Weights | Ceiling | Expected |
| --- | ---: | ---: | ---: |
| Qwen3-4B | 2.26 GB | ~68 tok/s | ~40–50 tok/s |
| Granite-4.2-8B or Ministral-3-8B | ~5–5.6 GB | ~28 tok/s | ~18–22 tok/s |
| Gemma-4-12B | 11 GB | ~14 tok/s | – |

- `guess`: a judgement with an 800-token prompt and 60 tokens of JSON takes about 1.5–3 s with the 4B model, so 300
  candidate links take about 8–15 minutes.

**Structured output:**
- `outlines` 1.3.3 declares `requires_python <3.14` (verified), so it will not install on 3.14.
- `xgrammar` has cp314 wheels, but 0.2.8 is 9 days old; 0.2.7 (2026-09-15) passes the 14-day rule.
- Simplest path: prompt for JSON at temperature 0, validate with Pydantic (already a backend dependency), retry once,
  and record failures explicitly.

### 2.5 Topic classification and datasets

**Models:**
- **`EuropeanParliament/EuroVoc`** (verified card): EUPL-1.2.
  - mmBERT-base encoder, 307M parameters, 1.23 GB safetensors plus a 21.7 MB `classifier.pt` and `mlb.pickle`.
    Those two are **pickles**: load them with `weights_only=True` or inspect them first.
  - All 24 EU languages; 7,062 concepts.
  - Micro-F1: domain level (21 domains) 0.733, micro-thesaurus level (127) 0.621, concept level 0.429. The card itself
    calls it a "tagging assistant".
  - **The multilingual version landed 2026-09-22** (commit `640f88e5…`) and HEAD `eea3ce448edc…` is 2026-09-23, both
    younger than 14 days.
  - The last older revision, `37751f5c7e8d0cd90e947b80c6cbf017575bf911` (2026-02-16), is the **English-only RoBERTa**
    version (0.46 GB).
- `jngb-labs/eurovoc-eubert` and `jngb-labs/eurovoc-bert-base`: apache-2.0, English, 18 and 13 downloads. Unproven.
- `delarosajav95/eurovoc-full-hierarchy-pipeline`: cc-by-4.0, `.bin` only.
- Zero-shot: `MoritzLaurer/bge-m3-zeroshot-v2.0` or mDeBERTa with label hypotheses. Alternatively, embed the
  EuroVoc labels with Qwen3-Embedding and take the nearest labels.
- **Practical point** (`reported`): every EUR-Lex act already carries Publications Office EuroVoc descriptors in its
  Cellar metadata, and the `EuropeanParliament/EuroVoc` dataset sample shows them as `eurovoc_concepts`. For
  *laws*, fetch the descriptors instead of predicting them. Classify only submissions and amendments, or propagate the
  law's topic to them.

**Datasets** (verified metadata):

| Dataset | Licence | Contents | Caveat |
| --- | --- | --- | --- |
| `coastalcph/multi_eurlex` (and `nlpaueb/multi_eurlex`) | cc-by-sa-4.0 | MultiEURLEX, 23 languages | **Loading-script dataset with no data files on the Hub**; the dataset viewer refuses it ("runs arbitrary python code"). Current `datasets` releases no longer run scripts (`reported`), so download the raw files the script points to |
| `NLP-AUEB/eurlex` (EURLEX57K) | cc-by-sa-4.0 | – | – |
| `pietrolesci/eurlex-57k` | none declared | 13 data files | – |
| `EuropeanParliament/EuroVoc` | eupl-1.2 | 5,937,976 documents with EuroVoc labels, 83 languages, monthly `jsonl.gz`; card says created 1 June 2026 | HEAD 2026-06-10 |
| `do-me/EUR-LEX` | cc-by-4.0 | 328k rows, 6.7 GB | **Updated weekly** (HEAD 2026-09-28): pin a revision |
| `ddrg/super_eurlex` | mit | 24 languages | – |
| `joelniklaus/eurlex_resources` | cc-by-4.0 | – | – |
| `mteb/eurlex-multilingual` | cc-by-sa-4.0 | MTEB retrieval task | – |
| `Helsinki-NLP/europarl` | licence `unknown` | – | – |

**Lobbying, amendment and consultation datasets.** I found **nothing EU-specific** on the Hub. Searches for
"lobbyplag", "parltrack", "transparency register", "have your say" and "amendments" returned no relevant datasets
(verified). Tangential ones:
- `mteb/legalbench_corporate_lobbying` (cc-by-4.0): US bills.
- `PiotrSty/rcl-legislacja-consultations`: Polish government consultations, licence "source-specific-rights-under-review".
- `demokratis/consultation-documents`: Swiss, no licence.
- `gemmozero/ai-lobbying-2026`: cc-by-nc-4.0.

The EU data has to come from the primary sources: the EP open data portal, Have Your Say and the Transparency
Register.

### 2.6 Translation

- **Is it needed at all?** Not for matching. Qwen3-Embedding, granite-r2 and bge-m3 are trained for cross-lingual
  retrieval (verified, from the cards' language claims), and mDeBERTa NLI accepts mixed-language pairs (card).
- Translation is useful only to *show* the jury a German or French submission next to an English amendment, and to
  feed the English-only large NLI model. Run it on demand for displayed links only.

| Repo id | Params | Weights | Licence | Notes |
| --- | --- | --- | --- | --- |
| `Helsinki-NLP/opus-mt-de-en`, `-fr-en`, … (one per pair) | ~75M | ~0.30 GB each; most are `.bin` only (fr-en has safetensors) | **apache-2.0 in HF metadata** (verified; the brief's "CC-BY 4.0" applies to the Tatoeba-Challenge `opus-mt-tc-*` models, `reported`) | Fast on CPU. A per-language list is needed |
| `Helsinki-NLP/opus-mt-mul-en` | ~77M | 0.31 GB `.bin` | apache-2.0 | One model for many languages; quality is lower (`reported`) |
| `facebook/m2m100_418M` / `_1.2B` | 418M / 1.2B | 1.94 / 4.96 GB `.bin` only | mit | Pickle weights |
| `google/madlad400-3b-mt` | 2.94B | 11.76 GB fp32 safetensors (GGUF 3.9 GB) | apache-2.0 | 419 languages; slow |
| `facebook/nllb-200-distilled-600M` | 600M | 2.46 GB | **cc-by-nc-4.0** | **Excluded** |
| `Unbabel/TowerInstruct-7B-v0.2` | 6.7B | – | **cc-by-nc-4.0** | **Excluded** |
| `google/translategemma-4b-it` | 5.0B | – | **gemma, gated** | **Excluded** |
| The LLM judge itself (Qwen3.5 lists 201 languages) | – | – | – | Can translate the one passage it is already judging, at no extra model cost |

### 2.7 PDF and document parsing

| Tool or model | Licence | Python 3.14 status (verified PyPI) | Notes |
| --- | --- | --- | --- |
| `pypdf` 6.19.0 (already in `backend/pyproject.toml`) | BSD-3-Clause | pure Python | Enough for most born-digital EU PDFs. Two-column reading order and tables are its weak points (`reported`) |
| `pypdfium2` 5.13.0 | BSD-3 / Apache-2.0 | `py3` wheel | PDFium text extraction; often better reading order (`reported`) |
| `pdfplumber` 0.11.10 | MIT | pure Python | Character positions, so you can split columns by x-coordinate and extract simple tables |
| `docling` 2.129.0 (2026-09-18; 2.132.0 is 2 days old), `docling-parse` 7.20.0, `docling-ibm-models` 4.0.3 | MIT | **cp314 wheels for docling-parse** | Models: `docling-project/docling-layout-heron` (apache-2.0, 42.9M parameters, 0.17 GB; sha `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`) and `docling-project/docling-models` (cdla-permissive-2.0 + apache-2.0, TableFormer). Speed `guess`: about 1–3 s/page on CPU with layout and tables; use it only on PDFs where pypdf output looks broken |
| `ibm-granite/granite-docling-258M` | apache-2.0 | – | 258M vision-language model, 0.52 GB, document-to-DocTags. Slower than docling's pipeline (`guess`: several s/page on MPS) |
| `marker-pdf` 2.0.0 / `surya-ocr` | code Apache-2.0 (PyPI) | pure Python | **Weights `datalab-to/*` are licensed `openrail`** (verified metadata); Datalab's modified OpenRAIL has commercial and revenue limits (`reported`). Avoid |
| `facebook/nougat-base` | **cc-by-nc-4.0** | – | **Excluded** |
| PaddleOCR 3.7.0 | Apache-2.0 | **`paddlepaddle` 3.3.1 has no cp314 wheel** (cp39–cp313 only) | Would force a separate 3.13 runtime. Only for scanned PDFs |
| PyMuPDF 1.28.2 | **AGPL-3.0** or commercial | abi3 wheel | Avoid: it can force AGPL terms on your distribution |

### 2.8 Organisation NER and entity resolution

| Repo id | Params | Weights | Licence | Languages | Created / modified | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `urchade/gliner_multi-v2.1` | 289M | 1.16 GB (safetensors added 2025-12-08) | apache-2.0 | multilingual | 2024-04-09 / 2025-12-08 | `gliner` 0.2.29 is pure Python. Zero-shot labels, e.g. "organization", "company", "trade association", "NGO", "public authority". Sha `443d26d654e0324125a96bebd8e796c14ff2efe6` |
| `fastino/gliner2-multi-v1` | 307M | 1.23 GB | apache-2.0 | – | 2025-12-04 / **2026-09-28** | HEAD has README-only commits from 2026-09-24 to 2026-09-28. Pin `edd4f6efd8611a4c29632fa8034b181ee8da9ebc` (2026-09-17). Uses the `gliner2` 2.0.0 package |
| `fastino/gliner2.5-multi-v1` | 287M | 1.15 GB | apache-2.0 | – | 2026-08-14 / 2026-09-28 | Newer; pin before 2026-09-19 |
| `Davlan/xlm-roberta-base-ner-hrl` | 277M | 1.11 GB | afl-3.0 (permissive) | 10 high-resource languages | 2022 / 2023-08-14 | Classic PER/ORG/LOC tagger; fixed labels |
| `Babelscape/wikineural-multilingual-ner` | 177M | – | **cc-by-nc-sa-4.0** | – | – | **Excluded** |

**Resolution (my recommendation):**
1. Key on Transparency Register IDs wherever the source gives them. Have Your Say feedback usually shows the
   organisation and register number (`reported`).
2. Otherwise normalise names: casefold, strip legal forms (e.V., GmbH, AISBL, asbl, S.A.), expand or keep acronyms.
3. Block candidate pairs with `rapidfuzz` (MIT, cp314 wheels) token-set ratio.
4. Confirm with cosine similarity on Qwen3-Embedding or granite-97m vectors for cross-language names, for example
   "Bundesverband der Deutschen Industrie" and "BDI".
5. Send ambiguous pairs to the LLM with both register entries side by side.

### 2.9 Stance and claim extraction (public statements vs requests)

- No open model targets EU policy stance. Candidates checked (verified):
  - ClimateBERT (`climatebert/distilroberta-base-climate-detector`, `-commitment`, `environmental-claims`,
    `netzero-reduction`): Apache-2.0 weights, but **trained on climatebert datasets licensed cc-by-nc-sa-4.0**
    (verified dataset metadata). English, paragraph-level, climate only.
  - `cardiffnlp/twitter-roberta-base-stance-climate`: tweets.
  - `ClimatePolicyRadar/national-climate-targets`.
  - `rwillh11/mdeberta_NLI_stance_NoContext`: no licence declared.
  - `bendavidsteel/Qwen3.5-4B-stance-detection`: licence not checked.
  - No InfluenceMap models on the Hub (verified search).
- **Recommended approach:**
  1. The LLM extracts `{actor, target_provision, requested_change, direction (strengthen/weaken/delete/add), evidence_quote}`
     from the consultation submission, and `{claim, topic, direction, quote}` from the press release.
  2. Pair the two by embedding similarity.
  3. Label each pair with NLI (entail, contradict, neutral) and an LLM verdict that must quote both texts.
- Show the quotes to the jury. Do not show model confidence as if it were a probability.

---

## 3. Minimal model kit for today

| # | Model (pin this revision) | Role(s) covered | Disk | RAM when loaded |
| --- | --- | --- | ---: | ---: |
| 1 | `Qwen/Qwen3-Embedding-0.6B` @ `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Candidate retrieval (step 2), entity-name matching (step 9), nearest-label topics (step 5), claim pairing (step 6) | 1.19 GB | ~1.2 GB fp16 on MPS / ~2.4 GB fp32 on CPU |
| 2 | `Qwen/Qwen3-Reranker-0.6B` @ `e61197ed45024b0ed8a2d74b80b4d909f1255473` | Reranking candidates (step 3, recall and order) | 1.19 GB | same as above |
| 3 | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` @ `b5113eb38ab63efdd7f280f8c144ea8b13f978ce` | Direction veto (step 3), survival check of a requested change against the final act's text (step 4), zero-shot topics (step 5), stance comparison (step 6) | 0.56 GB | ~1.1 GB fp32 |
| 4 | `mlx-community/Qwen3-4B-Instruct-2507-4bit` @ `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b` | JSON judge with quoted evidence (step 3), claim extraction (step 6), on-demand translation for display (step 7), ambiguous entity merges (step 9) | 2.26 GB | ~3–4 GB with KV cache |

**Totals** (`guess` for RAM): about **5.2 GB on disk** and about 6–9 GB of RAM with all four loaded. That leaves ample
headroom on 24 GB.

**Without models:**
- PDFs: `pypdf` / `pdfplumber`, with docling as an optional fallback.
- Law topics: EUR-Lex EuroVoc metadata.
- Entities: `rapidfuzz`.

**Optional fifth model:** `EuropeanParliament/EuroVoc`, only if you take a recorded exception for its 11-day-old
multilingual revision, or use the English-only `37751f5c…` revision.

**Install note (all verified on PyPI today). Python 3.14 does *not* force a separate 3.12 or 3.13 runtime.**

| Package | Version to pin | Wheel | Released |
| --- | --- | --- | --- |
| `torch` | 2.14.0 | cp314 + cp314t, macOS arm64 | 2026-09-02; 2.14.1 is 3 days old |
| `transformers` | 5.17.0 | pure Python | 2026-09-09; 5.18.0 is 3 days old |
| `sentence-transformers` | 6.1.0 | pure Python | 2026-09-18, 15 days old: just passes |
| `tokenizers` | 0.23.2 | abi3 | – |
| `safetensors` | 0.8.0 | abi3 | – |
| `sentencepiece` | 0.2.2 | cp314 | – |
| `numpy` | 2.5.3 | cp314 | – |
| `huggingface-hub` | 1.32.0 | – | 2026-09-17; 2.1.1, a new major version, is 2 days old |
| `mlx` / `mlx-metal` | 0.32.2 | cp314 | 2026-08-25; 0.32.3 is 4 days old |
| `mlx-lm` | **0.31.3** | – | 2026-04-22; 0.32.0 is 2 days old, so stay on 0.31.3, which supports `qwen3`, `qwen3_5`, `granite` and `mistral3` |
| `onnxruntime` | 1.30.0 | cp314 | – |
| `gliner` | 0.2.29 | pure Python | – |
| `rapidfuzz` | 3.14.6 | cp314 | – |
| `docling` | 2.129.0 | – | – |
| `docling-parse` | 7.20.0 | cp314 | – |

**What does not install on 3.14:**
- `llama-cpp-python`: sdist only, so it needs a C++/Metal build, which conflicts with the repository's
  `no-build = true`. Use mlx-lm instead.
- `paddlepaddle`: no cp314 wheel.
- `outlines`: declares `<3.14`.

**Evidence that this combination works:**
- `verified`: your earlier isolated runtime (`.claude/worktrees/agent-ad634323fc93c6463/backend/evaluation/runtime/pyproject.toml`)
  already ran `torch==2.14.0` and `transformers==5.17.0` on Python 3.14.7, with `exclude-newer` and `no-build`.
- `backend/pyproject.toml` already sets `exclude-newer = "14 days"` and `no-build = true`, so a separate model
  environment that copies those two settings picks the versions above automatically.

Suggested isolated environment:

```toml
# backend/evaluation/runtime/pyproject.toml (separate from the production lock)
[project]
requires-python = "==3.14.*"
dependencies = [
  "torch==2.14.0", "transformers==5.17.0", "sentence-transformers==6.1.0",
  "mlx==0.32.2", "mlx-lm==0.31.3", "rapidfuzz==3.14.6",
]
[tool.uv]
exclude-newer = "14 days"
no-build = true
```

Load every model with an explicit `revision=<sha>`. Prefer `use_safetensors=True`, which also rules out the
pickle-only repositories (bge-m3, opus-mt, m2m100, legal-bert). Set `HF_HUB_OFFLINE=1` after the first download so the
19:00 run cannot fetch a new revision.

---

## 4. Risks

### Licences
- **Excluded as non-commercial:** jina embeddings v3 and v5, jina rerankers v2 and v3, NLLB-200, TowerInstruct,
  nougat, Babelscape wikineural (all verified).
- **Gated or with use terms:**
  - `google/embeddinggemma-300m`, `google/gemma-3-*` and `google/translategemma-4b-it`: `gemma` licence, manual gate.
  - `utter-project/EuroLLM-9B-Instruct`: auto gate.
  - `datalab-to/*` (marker and surya weights): `openrail`.
- **Gemma 4 is now Apache-2.0** (verified metadata on `google/gemma-4-12B-it` and `gemma-4-E4B-it`). Do not assume
  all Gemma models carry the old terms; check each repository.
- **Copyleft:** PyMuPDF (AGPL). EUPL-1.2 on the EuroVoc model and dataset is OSI-approved copyleft and compatible with
  an open repository, but name it in the README.
- **Training-data provenance:**
  - ClimateBERT classifiers are Apache-2.0 but trained on cc-by-nc-sa data.
  - The MoritzLaurer models without `-c` include data with mixed licences (per their own cards). The 2mil7 model is
    trained on machine translations of MNLI, ANLI, FEVER and others; ANLI's licence is CC-BY-NC (`reported`).
  - State this in the README rather than claiming everything is clean.
- **No licence declared:** `Stern5497/sbert-legal-xlm-roberta-base`, `pietrolesci/eurlex-57k`,
  `demokratis/consultation-documents`, `mlx-community/Qwen3.5-4B-4bit` (fall back to the base model's licence),
  `mlx-community/gemma-4-12B-it-qat-4bit`.

### Revisions younger than 14 days (HEAD after 2026-09-19)

| Repository | HEAD date | What to pin instead |
| --- | --- | --- |
| `EuropeanParliament/EuroVoc` (model) | 2026-09-23 | The multilingual model itself is from 2026-09-22. Only the English-only `37751f5c7e8d0cd90e947b80c6cbf017575bf911` passes |
| `fastino/gliner2-multi-v1` | 2026-09-28 | `edd4f6efd8611a4c29632fa8034b181ee8da9ebc` |
| `fastino/gliner2.5-multi-v1` | 2026-09-28 | A commit before 2026-09-19 |
| `do-me/EUR-LEX` (dataset) | 2026-09-28 | A commit before 2026-09-19 |

Everything in the minimal kit has a HEAD older than 14 days. The newest is `Qwen/Qwen3-Embedding-0.6B` at 2026-04-20.

Some packages are also inside the window: torch 2.14.1, transformers 5.18.0, mlx 0.32.3, mlx-lm 0.32.0,
huggingface-hub 2.x, docling 2.130 and later, docling-parse 7.22 and xgrammar 0.2.8. The repository's
`exclude-newer = "14 days"` setting keeps them out.

### Remote code
`gte-multilingual-base`, `gte-multilingual-reranker-base`, `nomic-embed-text-v2-moe` and `jina-reranker-v3` declare
`auto_map`, so they need `trust_remote_code=True` (verified). That executes repository Python at load time: avoid
them, or pin and read the code first.

### Pickle weights
These repositories ship `.bin`/`.pt` and no safetensors: `BAAI/bge-m3`, `Helsinki-NLP/opus-mt-*` (most pairs),
`facebook/m2m100_*`, `nlpaueb/*`. The EuroVoc model ships `classifier.pt` and `mlb.pickle`. Use `weights_only=True`
or switch to a safetensors alternative.

### Memory: 24 GB is the real ceiling for LLMs
`reported`: macOS lets the GPU wire only part of unified memory by default, roughly two-thirds to three-quarters.
Raising that limit means changing a system setting (`iogpu.wired_limit_mb`), which you should not do on the demo
machine. That rules out:
- 4-bit Qwen3-30B-A3B (17.2 GB) and Qwen3.6-35B-A3B (20.4 GB);
- 4-bit Gemma-4-12B (11 GB) loaded alongside the other models.

### MPS quirks (`reported`)
- Some operators fall back to CPU or raise errors without `PYTORCH_ENABLE_MPS_FALLBACK=1`.
- fp16 on MPS gives slightly different scores from CPU fp32. DeBERTa-v3 can overflow in fp16; keep NLI on CPU fp32.
- bf16 coverage on MPS is incomplete, so load Qwen weights as fp16 or fp32 on MPS.
- MPS kernels are not guaranteed deterministic.

### Determinism
- Record model sha, package versions, dtype, device, thread count, `max_length` and batch size with every score, as
  `qwen-results.json` already does.
- For bit-stable reruns, run the scored path on CPU fp32 with `torch.use_deterministic_algorithms(True)` and fixed
  threads.
- Padding and batch composition change scores slightly. Fix the batch size, or score one item at a time for the 60
  submitted pairs.
- MLX greedy decoding (temperature 0) repeats on the same machine and versions, but not necessarily across mlx
  releases. Cache LLM verdicts to disk and keep them separate from human labels.

### Benchmark caveats
- Most scores in this report are the vendors' own (the Qwen card compares Qwen to others, Granite's card compares
  Granite). The MTEB subsets differ between cards.
- None of these benchmarks measures *legal-change direction*. Accept any swap only on your practice harness
  (precision in the top 20, recall, AUC on organisation-grouped folds), as `AGENTS.md` requires.

### Time budget
Embedding all 540k amendments with a 0.6B model is an hours-long job on this laptop (`guess`, section 2.1). For
tonight, restrict the run to the demo laws, or use `granite-embedding-97m-multilingual-r2` for the full corpus.

---

## Sources

- Hugging Face model and dataset API, with `?blobs=true` and `/commits/main`, for every repository id above, plus each
  repository's `raw/main/README.md` (read 2026-10-03).
- PyPI JSON API (`https://pypi.org/pypi/<package>/json`) for torch, transformers, sentence-transformers, tokenizers,
  safetensors, huggingface-hub, mlx, mlx-metal, mlx-lm, mlx-vlm, mlx-embeddings, onnxruntime, llama-cpp-python,
  docling, docling-parse, docling-ibm-models, gliner, gliner2, pypdf, pymupdf, pdfplumber, pypdfium2, sentencepiece,
  numpy, scipy, scikit-learn, rapidfuzz, flagembedding, marker-pdf, surya-ocr, paddleocr, paddlepaddle, outlines and
  xgrammar.
- GitHub `ml-explore/mlx-lm` contents of `mlx_lm/models` at tag `v0.31.3`.
- Apple ML Research, "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU":
  https://machinelearning.apple.com/research/exploring-llms-mlx-m5 (`reported`: bandwidth and speed-ups).
- Gist by awni (mlx-lm benchmarks on M4 Max): https://gist.github.com/awni/c1790e4c3a39be6e8f1c4afd42423d2d
  (`reported`).
- Repository files: `backend/evaluation/qwen-results.json`, `backend/evaluation/README.md`, `backend/pyproject.toml`.
