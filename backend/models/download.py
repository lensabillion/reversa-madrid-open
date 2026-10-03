"""Fetch only pinned public safe weights and tokenizer assets, never repository code."""

import argparse

from embed import MODELS

# The installed hub overload has untyped optional parameters that we do not use.
from huggingface_hub import snapshot_download  # pyright: ignore[reportUnknownVariableType]
from judge import MODEL_ID, REVISION

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=(*MODELS, "judge"))
    args = parser.parse_args()
    model_id, revision = (MODEL_ID, REVISION) if args.model == "judge" else MODELS[args.model]
    path = snapshot_download(
        model_id,
        revision=revision,
        allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors"],
        max_workers=2,
    )
    print(path)
