"""One-time online model download. Runtime app.py only loads this local directory."""
from pathlib import Path
from huggingface_hub import snapshot_download

REPOSITORY = "fastino/gliner2-privacy-filter-PII-multi"
DESTINATION = Path(__file__).parent / "models" / "fastino-gliner2-privacy-filter-PII-multi"

snapshot_download(repo_id=REPOSITORY, local_dir=DESTINATION)
print(f"Downloaded {REPOSITORY} to {DESTINATION}")
