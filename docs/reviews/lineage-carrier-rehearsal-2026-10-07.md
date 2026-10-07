# Exact lexical carrier evidence: four-law rehearsal

Measured on 7 October 2026 for `rev-0q9m`. New matching rules bind an earlier consultation
quotation to the exact amendment and final-law interval that carries it. They replace the
old join through a merged phrase, which could associate a document with adjacent but
unrelated amendment wording. This is a structural repair, not an independent precision audit.

## Inputs and method

Compared baseline `50dd222` with backend revision `3e4a2d8` on the same completed local
collection bundles. Both runs call `load_collected` and `build_lineage` directly, with a
fixed output timestamp of `2026-10-07T00:00:00Z` and no judge. They do not call collection,
network clients or paid models. Generated views went to separate temporary directories;
no saved website view was overwritten. The generated measurement record is
[`backend/evaluation/lineage-carrier-evidence.json`](../../backend/evaluation/lineage-carrier-evidence.json).

Hardware: Apple M5, arm64, macOS 26.6.2, Python 3.14.7. Times below are one cached generation
observation per revision, excluding bundle loading, collection and downloads. The two
runs overlapped, so these observations do not establish a performance improvement or
regression. They also do not measure the end-to-end “any law” requirement.

## Results

“Eligible documents” means distinct consultation documents with at least one earlier,
non-citation origin attached to an adopted phrase. It does not mean verified authorship.

| Law | Amendments | Consultation documents | Adopted phrases, unchanged | Eligible documents before → after | New exact supports | Generation seconds before → after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Digital Services Act, 2020/0361(COD) | 6,476 | 3,516 | 275 | 10 → 5 | 9 | 4.453 → 4.353 |
| Digital Markets Act, 2020/0374(COD) | 3,261 | 305 | 113 | 9 → 9 | 50 | 1.980 → 1.976 |
| Artificial Intelligence Act, 2021/0106(COD) | 5,660 | 788 | 631 | 60 → 41 | 154 | 4.167 → 4.297 |
| Data Act, 2022/0047(COD) | 2,437 | 1,009 | 196 | 13 → 8 | 8 | 2.251 → 2.421 |

Counts of origin records are not directly a count of claims: the new representation can
retain distinct occurrences that the old phrase-level grouping collapsed. The Digital
Markets Act has 12 old adopted-origin records and 17 new records while still representing
nine eligible documents. The other laws have 10 → 5, 93 → 57 and 17 → 8 adopted-origin
records respectively. Fewer records alone do not prove higher precision.

## Verified invariants

- All 221 supports passed three independent raw-source slice comparisons: 663 exact
  submission, amendment and final-text quotations.
- All 328 files in the four input bundles retained their content hashes and modification
  times in each run. Outputs were written only under a temporary directory.
- Adopted phrase records, holder-credit records and tabled phrase records are identical.
  Amendment metadata is identical when joined by amendment ID. The new adoption array is
  sorted by ID; comparing array positions alone therefore gives a false difference.
- Changed and linked word counts remain unchanged for every law. The change concerns
  the consultation-to-carrier support, not the covered final-law word union.

The backend gate separately passed 679 tests, 100% line and branch coverage (4,194
statements, 1,156 branches), Ruff and strict types. An independent Astra review ran a
seeded 400-case interval oracle (seed 20707) and checked 569 source spans. These are
algorithm/contract checks, not human judgments of real-world influence.

The integrated frontend passed 83 tests, strict types, Biome and a production build.
Independent Astra review checked support-ID joins, graph focus, legacy unavailable states
and saved-count consistency. A browser rehearsal on the generated Digital Markets Act
view verified the experimental notice, graph focus and submission/amendment/final quotes.
Random sampling is explicitly unavailable pending the displayed-scope repair (R5).

## Reproducing the generation boundary

Run the following through the backend's locked environment with a completed collection
bundle. Repeat in each revision with different output directories. The fixed timestamp
makes saved output hashes comparable. Preserve source data and never point `output` at
the input bundle when performing a comparison.

```python
from datetime import UTC, datetime
from pathlib import Path
from influence.services.collected import load_collected
from influence.services.lineage_assembly import build_lineage, write_lineage

bundle = Path("/path/to/data/laws/2021-0106-COD")
output = Path("/tmp/influence-rehearsal/revision/2021-0106-COD")
output.mkdir(parents=True, exist_ok=True)
view = build_lineage(load_collected(bundle), generated_at=datetime(2026, 10, 7, tzinfo=UTC))
write_lineage(view, output)
```

## Limits and follow-ups

The preserved holder credits still operate on merged adopted phrases; this repair does
not change their whole-credit semantics. R3 (`rev-h5zb`) separately binds semantic origins
to surviving targets. Frontend joins must use each support's own amendment and final span;
`lineage-2` alone does not imply that an origin has support. Legacy snapshots and unsupported
semantic suggestions must remain explicit. No independent human audit, recall estimate,
paid semantic evaluation or fresh-download rehearsal was performed here.
