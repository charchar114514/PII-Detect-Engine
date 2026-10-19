"""Explicit online setup; normal service startup never downloads spaCy models."""
import subprocess
import sys

from spacy.util import is_package

from pii_engine.config import load_presidio_config


if __name__ == "__main__":
    for model in dict.fromkeys(load_presidio_config().models.values()):
        if is_package(model):
            print(f"Already installed: {model}")
        else:
            subprocess.run([sys.executable, "-m", "spacy", "download", model], check=True)
