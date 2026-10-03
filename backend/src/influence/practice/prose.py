"""Two scorers that treat a proposal as prose: the baseline the assessor had, and phrase coverage.

LobbyPlag's proposals carry old and new wording, which is not what a real submission gives
us: a passage of prose with no known original. Both scorers here read only the proposal's
new wording, as if it were a passage quoted from a position paper, so the harness measures
how well each one finds the true source when the original is unknown.

* `prose_dice_scores`: the edit scorer's symmetric overlap against the whole passage. This is
  what `assess_link` computed for prose before phrase coverage.
* `prose_coverage_scores`: the share of the amendment's inserted words that the passage
  repeats as phrases of three or more words, weighted by rarity (`services/prose_match.py`).
"""

from collections.abc import Sequence

from influence.practice.labels import LabelledPair, PracticePair
from influence.schemas.scoring import ScoreRequest, TextChange
from influence.services.prose_match import match_prose, rarity_weights, words_of
from influence.services.scoring import changed_spans, score_pair


def prose_dice_scores(
    _training: Sequence[LabelledPair], test: Sequence[PracticePair]
) -> list[float]:
    """The edit scorer with the proposal's new wording as an insertion; 0 where it cannot run."""
    scores: list[float] = []
    for pair in test:
        try:
            request = ScoreRequest(
                amendment=TextChange(old=pair.amendment.old, new=pair.amendment.new),
                submission=TextChange(old="", new=pair.submission.new),
            )
        except ValueError:
            scores.append(0.0)
        else:
            scores.append(score_pair(request).score)
    return scores


def prose_coverage_scores(
    _training: Sequence[LabelledPair], test: Sequence[PracticePair]
) -> list[float]:
    """Rarity-weighted phrase coverage of the amendment's inserted words in the proposal text.

    Rarity comes from the test pairs' proposal texts alone, which are unlabelled, so no label
    reaches the score. 0 for an amendment with no inserted words or text the edit scorer's
    bounds refuse.
    """
    rarity = rarity_weights(pair.submission.new for pair in test)
    scores: list[float] = []
    for pair in test:
        try:
            inserted = [
                span.text
                for span in changed_spans(
                    TextChange(old=pair.amendment.old, new=pair.amendment.new)
                )
                if span.operation == "insert"
            ]
        except ValueError:
            scores.append(0.0)
            continue
        amendment_words = [word.text for text in inserted for word in words_of(text)]
        passage_words = [word.text for word in words_of(pair.submission.new)]
        scores.append(match_prose(amendment_words, passage_words, rarity).coverage)
    return scores
