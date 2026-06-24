import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker.seed_gardas import load_seed_manifest


def test_load_seed_manifest_validates_artifact_metadata(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("bir\niki\n", encoding="utf-8", newline="\n")
    raw = corpus.read_bytes()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "test-v1",
                "corpus": {
                    "name": "gardas_test",
                    "text_path": str(corpus),
                    "line_count": 2,
                    "raw_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "frozen": True,
                    "format": "text",
                },
                "mixture": [{"name": "test", "share": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    seed = load_seed_manifest(manifest)

    assert seed["name"] == "gardas_test"
    assert seed["declared_byte_size"] == len(raw)
    assert seed["declared_line_count"] == 2
    assert seed["metadata"]["frozen"] is True


def test_load_seed_manifest_rejects_size_mismatch(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("data", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "corpus": {
                    "name": "bad",
                    "text_path": str(corpus),
                    "line_count": 1,
                    "raw_bytes": 999,
                    "sha256": "0" * 64,
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="File size mismatch"):
        load_seed_manifest(manifest)
