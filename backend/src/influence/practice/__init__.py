"""The architecture's practice loop: it trains and checks part 4, the score combiner.

It reads LobbyPlag's labelled historical pairs, splits them into grouped folds, calls a
scorer, and reports the hidden test's metrics on simulated 30 + 30 tests. Labels flow only
into the measurement; no score ever reads one (explainer §11, "Raw model output stays
separate from labels"). Run it with `python -m influence.practice`.
"""
