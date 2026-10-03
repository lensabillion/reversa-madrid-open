# Research for the Influence Atlas, 3 October 2026

Four research reports written by delegated research agents between about 10:40 and 11:10
CEST on 3 October 2026, the morning the organizers replaced the Challenge 03 brief. The
[Atlas explainer](../../explainer/influence-atlas-primer.md) summarises them; read it first.

| Report | Question |
| --- | --- |
| [data-sources.md](data-sources.md) | Which public sources give the 2019+ record, through which routes, and how they join from a procedure number |
| [methods.md](methods.md) | How to find candidates, verify links, trace outcomes, resolve actors, compare public voice with asks, forecast, classify topics and handle languages |
| [hf-models.md](hf-models.md) | Which open Hugging Face models fit each role, with licences, sizes, revisions and Python 3.14 wheels |
| [strategy.md](strategy.md) | How to maximise each of the jury's criteria, what is publicly known about who shaped 2019+ laws, the demo script, the report outline and cut lines |

How to read them:

- Each report tags its claims `verified` (primary source read or request made that
  morning), `measured` (run on the team laptop, an Apple M5 with 24 GB), `reported`
  (secondhand) and `estimate` or `guess`. Re-check a `reported` claim before quoting it in
  the public report.
- They are snapshots. Statements about the repository's state (for example, that
  `AGENTS.md` still described the CSV deliverables, or the hidden-pair labelling rule)
  describe the checkout at that moment; the same change that added these reports updated
  those files.
- The benchmark scripts mentioned in `methods.md` (`bench.py`, `embbench.py`) ran in a
  temporary directory and are not committed, in line with PR #18 (no research code outside
  the gates). Re-measure under the gates when part 3 is built.
- Package versions younger than 14 days (for example `torch` 2.14.1, used in one
  benchmark) are not approved for the project's environments; `hf-models.md` lists the
  versions that pass the supply-chain rule.
