# Atlas Contract Fixtures

An invented two-law bundle, one JSON Lines file per record type of
[`schemas/atlas.py`](../../../src/influence/schemas/atlas.py), schema version `atlas-1`.
Parts 3 to 8 build against it while real collection is still running.

Everything here is made up: procedures `2099/0001(COD)` and `2099/0002(COD)`, the actors,
the texts and the scores. A test that passes on these files proves a consumer reads the
contract, not that any method is accurate.

The files are generated. Do not edit them: change
[`tests/atlas_fixture.py`](../../atlas_fixture.py) and run

```sh
uv run --directory backend --locked python tests/atlas_fixture.py
```

`tests/test_atlas_contracts.py` fails while the committed files differ from the builder.

## Cases

`cases.json` maps each case to the record that shows it.

| Case | Record | What a consumer must handle |
| --- | --- | --- |
| Supported copy | `link:a-am1-makers` | A published link with exact spans on both sides, traced to a renumbered final article |
| Opposite request | `link:a-am1-watch` | Shared words, opposite meaning: status `contradicted`, never an edge |
| Short shall/may edit | `link:a-am2-city` | A one-word change kept and assessed, `unconfirmed` |
| Ambiguous actor | `actor:name:hys_feedback.acme` | A name matching two register entries: `candidate_ids`, no `register_id` |
| Missing date | `link:a-am1-undated` | Same wording as the supported copy, but `unknown_date`, so not published |
| Missing final act | `outcome:b-ask-labels-final` | `result: unknown` with a reason; the law's `final_act` layer is `missing` |
| Partial outcome | `outcome:a-ask-city-final` | `result: partial` with the final article's span |

## Reading Rules

- A span's `start` and `end` are Unicode code-point offsets into the text of `record_id`'s
  `field`: a document's text is in `document_texts.jsonl`, an amendment's `new_text` and
  `old_text` and an article's `text` are on the record. In TypeScript, slice with
  `Array.from(text).slice(start, end)`.
- `null` means unknown. `old_text: null` is an unknown original; `""` is an insertion.
  A coverage `count` of `null` is not zero.
- Every ask has outcomes, including asks with no published link.
- `graphs.jsonl` holds one snapshot built from published links only.
