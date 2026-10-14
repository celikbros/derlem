"""TASK-050: secimden belge cikarma (``selection subtract``), yeniden turetmeden.

Ana iddia: subtract = cikarma listesiyle yeniden turetme (``clean_candidate
--post-dedup-drop``): secim listesi, karar dosyasi ve uretilen metin bayt bayt ayni;
held-out degismez; yeni metin = eski metin eksi dusen satirlar. Dusen belge tekrar
kayitlarinda kalir: onun normalize kopyasi ve yakin kopyasi yine reddedilir (dusen
belge baska kaynakta yasiyor; kopyasi aday'a girerse kapi yine takilir).

Belirsiz ya da bolum disi cikarma (held-out belgesi, satir numarasi / doc_id tutmuyor,
train bolmesinin sonunu asan, iki kez listelenen, secimde iki kez gecen doc_id)
reddedilir ve hicbir cikti kalmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from derlem_worker.clean_candidate import (
    derive_clean_candidate,
    derive_selection_list,
    selection_artifact_paths,
)
from derlem_worker.document_record import (
    DECISION_SCHEMA,
    ParquetRowWriter,
    read_decisions,
    read_selection,
    validate_decision,
)
from derlem_worker import selection as selection_module
from derlem_worker.selection import SUBTRACT_METHOD, SelectionError, materialize, subtract

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_clean_candidate_shards import (  # noqa: E402 - ayni fikstur (TASK-049)
    ANKARA,
    DECIDED_AT,
    NEAR_BASE,
    RUN_ID,
    _build_store,
    _fixture_documents,
    _options,
)

DROP_RUN_ID = "task-050-test-drop"
DROP_DECIDED_AT = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
DROP_REASON = "cross_source_normalized_duplicate;sources=00000000-0000-0000-0000-000000000001"


def _train_lines(selection_path: Path) -> list[dict]:
    return [row for row in read_selection(selection_path) if row["partition"] == "train"]


def _held_out_rows(selection_path: Path) -> list[dict]:
    return [row for row in read_selection(selection_path) if row["partition"] == "held_out"]


def _drop_row(doc_id: str, line: int, **overrides) -> dict:
    row = {
        "doc_id": doc_id,
        "source_ordinal": line,
        "decision_type": "duplicate",
        "verdict": "reject",
        "reason": DROP_REASON,
        "judge": "normalized-document-sha256-v1",
        "run_id": DROP_RUN_ID,
        "decided_at": DROP_DECIDED_AT,
    }
    row.update(overrides)
    return row


def _write_drops(path: Path, rows: list[dict]) -> Path:
    writer = ParquetRowWriter(path, DECISION_SCHEMA, row_group_size=100_000, validator=validate_decision)
    for row in rows:
        writer.add(row)
    writer.close()
    return path


def _base(tmp_path: Path, documents=None) -> tuple[dict, Path, Path]:
    manifest_object, store_root, _ = _build_store(tmp_path, documents or _fixture_documents())
    (tmp_path / "base").mkdir()
    manifest = derive_selection_list(
        manifest_object, tmp_path / "base" / "aday.jsonl", source=None, store_root=store_root,
        run_id=RUN_ID, decided_at=DECIDED_AT, **_options(),
    )
    return manifest, manifest_object, store_root


def _drops_for(manifest: dict, tmp_path: Path, lines: list[int]) -> Path:
    train = _train_lines(Path(manifest["selection"]["path"]))
    return _write_drops(tmp_path / "drop.parquet", [_drop_row(train[line - 1]["doc_id"], line) for line in lines])


def _outputs(prefix: Path) -> list[Path]:
    return [prefix.with_name(prefix.name + suffix)
            for suffix in (".selection.parquet", ".decisions.parquet", ".selection.manifest.json")]


# --------------------------------------------------------------------------
# Esdegerlik: subtract = cikarma listesiyle yeniden turetme
# --------------------------------------------------------------------------


def test_subtract_equals_rederive_with_post_dedup_drop(tmp_path: Path) -> None:
    manifest, manifest_object, store_root = _base(tmp_path)
    train = _train_lines(Path(manifest["selection"]["path"]))
    assert len(train) == 4
    # Aday satiri 1 = ANKARA (sonra normalize kopyasi var), 3 = NEAR_BASE (sonra yakin kopyasi var).
    drop = _drops_for(manifest, tmp_path, [1, 3])

    result = subtract(Path(manifest["manifest_path"]), drop, tmp_path / "sub" / "aday")
    (tmp_path / "re").mkdir()
    rederived = derive_selection_list(
        manifest_object, tmp_path / "re" / "aday.jsonl", source=None, store_root=store_root,
        run_id=RUN_ID, decided_at=DECIDED_AT, post_dedup_drop_path=drop, **_options(),
    )
    re_files = selection_artifact_paths((tmp_path / "re" / "aday.jsonl").resolve())
    sub_selection, sub_decisions, _ = _outputs(tmp_path / "sub" / "aday")

    assert sub_selection.read_bytes() == re_files["selection"].read_bytes()
    assert sub_decisions.read_bytes() == re_files["decisions"].read_bytes()
    assert result["expected_materialization"] == rederived["expected_materialization"]
    assert result["decisions"]["counts"] == rederived["decisions"]["counts"]
    assert result["selection"]["partitions"] == rederived["selection"]["partitions"] == {"held_out": 1, "train": 2}
    assert rederived["report"]["removed_post_dedup_drop_lines"] == 2

    # Metin: iki materialize ayni, metin-kopya yeniden turetmeyle ayni, eski metin eksi dusenler.
    (tmp_path / "copy").mkdir()
    copy = derive_clean_candidate(
        manifest_object, tmp_path / "copy" / "aday.jsonl", source=None, store_root=store_root,
        post_dedup_drop_path=drop, **_options(),
    )
    texts = []
    for name in ("old", "m1", "m2"):
        (tmp_path / name).mkdir()
        source_manifest = manifest["manifest_path"] if name == "old" else result["manifest_path"]
        materialize(
            Path(source_manifest), output_path=tmp_path / name / "aday.jsonl",
            held_out_output_path=tmp_path / name / "aday_heldout.jsonl", verify_parent=True,
        )
        texts.append((tmp_path / name / "aday.jsonl").read_bytes())
    old, first, second = texts
    assert first == second == (tmp_path / "copy" / "aday.jsonl").read_bytes()
    assert copy.output_sha256 == result["expected_materialization"]["train"]["sha256"]
    old_lines = old.splitlines(keepends=True)
    assert b"".join(line for index, line in enumerate(old_lines, 1) if index not in {1, 3}) == first
    for name in ("m1", "m2", "copy"):
        assert (tmp_path / name / "aday_heldout.jsonl").read_bytes() == (tmp_path / "old" / "aday_heldout.jsonl").read_bytes()


def test_subtract_keeps_held_out_and_dedup_state_and_records_itself(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    old_selection = Path(manifest["selection"]["path"])
    drop = _drops_for(manifest, tmp_path, [1, 3])
    result = subtract(Path(manifest["manifest_path"]), drop, tmp_path / "sub" / "aday")
    new_selection, new_decisions, new_manifest_path = _outputs(tmp_path / "sub" / "aday")

    assert _held_out_rows(new_selection) == _held_out_rows(old_selection)
    assert result["expected_materialization"]["held_out"] == manifest["expected_materialization"]["held_out"]
    assert result["parent"] == manifest["parent"]
    old_train = _train_lines(old_selection)
    assert [row["source_ordinal"] for row in _train_lines(new_selection)] == [
        old_train[1]["source_ordinal"], old_train[3]["source_ordinal"]]

    decisions = list(read_decisions(new_decisions))
    # Eski satirlar aynen, sirasi korunarak; dusenler ebeveyn sira numarasiyla yerinde.
    assert [row for row in decisions if row["run_id"] == RUN_ID] == list(
        read_decisions(Path(manifest["decisions"]["path"])))
    added = [row for row in decisions if row["run_id"] == DROP_RUN_ID]
    assert [row["source_ordinal"] for row in added] == [old_train[0]["source_ordinal"], old_train[2]["source_ordinal"]]
    assert all(row["reason"] == DROP_REASON and row["decided_at"] == DROP_DECIDED_AT for row in added)
    ordinals = [row["source_ordinal"] for row in decisions]
    assert ordinals == sorted(ordinals)
    # Dusen ANKARA'nin normalize kopyasi ve NEAR_BASE'in yakin kopyasi reddedilmis kalir.
    reasons = {row["reason"] for row in decisions if row["decision_type"] in {"duplicate", "near_duplicate"}}
    assert f"normalized_duplicate_of={old_train[0]['source_ordinal']}" in reasons
    assert f"near_duplicate_of={old_train[2]['source_ordinal']}" in reasons

    recorded = json.loads(new_manifest_path.read_text(encoding="utf-8"))
    section = recorded["subtraction"]
    assert section["method"] == SUBTRACT_METHOD and section["dropped"] == 2
    assert section["input_selection"]["sha256"] == manifest["selection"]["sha256"]
    assert section["input_decisions"]["sha256"] == manifest["decisions"]["sha256"]
    assert section["drop"]["sha256"] == hashlib.sha256(drop.read_bytes()).hexdigest()
    assert section["drop"]["run_ids"] == [DROP_RUN_ID]
    assert section["dropped_parent_ordinals"] == [old_train[0]["source_ordinal"], old_train[2]["source_ordinal"]]
    assert section["rejections_referencing_dropped"] == {"duplicate:reject": 1, "near_duplicate:reject": 1}
    assert section["input_expected_materialization"] == manifest["expected_materialization"]
    assert recorded["selection"]["sha256"] == hashlib.sha256(new_selection.read_bytes()).hexdigest()
    assert recorded["decisions"]["sha256"] == hashlib.sha256(new_decisions.read_bytes()).hexdigest()
    assert recorded["decisions"]["counts"]["duplicate:reject"] == manifest["decisions"]["counts"]["duplicate:reject"] + 2
    assert recorded["expected_materialization"]["train"]["lines"] == 2


def test_subtract_is_deterministic(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    drop = _drops_for(manifest, tmp_path, [2])
    first = subtract(Path(manifest["manifest_path"]), drop, tmp_path / "a" / "aday")
    second = subtract(Path(manifest["manifest_path"]), drop, tmp_path / "b" / "aday")
    for left, right in zip(_outputs(tmp_path / "a" / "aday")[:2], _outputs(tmp_path / "b" / "aday")[:2]):
        assert left.read_bytes() == right.read_bytes()
    assert first["expected_materialization"] == second["expected_materialization"]


# --------------------------------------------------------------------------
# Reddedilenler: belirsiz / bolum disi; hicbir cikti kalmaz
# --------------------------------------------------------------------------


def _refused(manifest: dict, drop: Path, prefix: Path, match: str) -> None:
    with pytest.raises(SelectionError, match=match):
        subtract(Path(manifest["manifest_path"]), drop, prefix)
    assert not any(path.exists() for path in _outputs(prefix))
    assert not list(prefix.parent.glob("*.tmp")) if prefix.parent.exists() else True


def test_held_out_document_cannot_be_subtracted(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    held = _held_out_rows(Path(manifest["selection"]["path"]))[0]
    drop = _write_drops(tmp_path / "drop.parquet", [_drop_row(held["doc_id"], 1)])
    _refused(manifest, drop, tmp_path / "out" / "aday", "held_out partition")


def test_line_number_and_doc_id_must_agree(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    train = _train_lines(Path(manifest["selection"]["path"]))
    drop = _write_drops(tmp_path / "drop.parquet", [_drop_row(train[2]["doc_id"], 2)])
    _refused(manifest, drop, tmp_path / "out" / "aday", "names doc_id")


def test_drop_beyond_the_train_partition_is_refused(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    drop = _write_drops(tmp_path / "drop.parquet", [_drop_row("ab" * 32, 5)])
    _refused(manifest, drop, tmp_path / "out" / "aday", "beyond the train partition")


def test_foreign_doc_id_is_refused(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    drop = _write_drops(tmp_path / "drop.parquet", [_drop_row("ab" * 32, 2)])
    _refused(manifest, drop, tmp_path / "out" / "aday", "names doc_id")


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ("same_line", "listed twice"),
        ("same_doc", "listed twice"),
        ("not_reject", "not a reject"),
        ("no_line", "no candidate line number"),
    ],
)
def test_ambiguous_or_malformed_drop_lists_are_refused(tmp_path: Path, rows: str, match: str) -> None:
    manifest, _, _ = _base(tmp_path)
    train = _train_lines(Path(manifest["selection"]["path"]))
    cases = {
        "same_line": [_drop_row(train[0]["doc_id"], 1), _drop_row(train[1]["doc_id"], 1)],
        "same_doc": [_drop_row(train[0]["doc_id"], 1), _drop_row(train[0]["doc_id"], 2)],
        "not_reject": [_drop_row(train[0]["doc_id"], 1, verdict="flag")],
        "no_line": [_drop_row(train[0]["doc_id"], None)],
    }
    drop = _write_drops(tmp_path / "drop.parquet", cases[rows])
    _refused(manifest, drop, tmp_path / "out" / "aday", match)


def test_doc_id_occurring_twice_in_the_selection_is_ambiguous(tmp_path: Path) -> None:
    # Kisa (parmak izi alinmayan) ayni satir iki kez train'e girer: doc_id iki kez gecer.
    parent = tmp_path / "girdi.txt"
    parent.write_bytes("kısa satır\nbaşka bir kısa satır\nkısa satır\n".encode("utf-8"))
    (tmp_path / "base").mkdir()
    manifest = derive_selection_list(
        parent, tmp_path / "base" / "aday.txt", source=None, max_document_bytes=4096,
        run_id=RUN_ID, decided_at=DECIDED_AT,
    )
    train = _train_lines(Path(manifest["selection"]["path"]))
    assert train[0]["doc_id"] == train[2]["doc_id"]
    drop = _write_drops(tmp_path / "drop.parquet", [_drop_row(train[0]["doc_id"], 1)])
    _refused(manifest, drop, tmp_path / "out" / "aday", "occurs 2 times")
    with pytest.raises(ValueError, match="names candidate line 1"):
        derive_selection_list(
            parent, tmp_path / "re" / "aday.txt", source=None, max_document_bytes=4096,
            run_id=RUN_ID, decided_at=DECIDED_AT, post_dedup_drop_path=drop,
        )


def test_tampered_inputs_and_existing_outputs_are_refused(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    drop = _drops_for(manifest, tmp_path, [1])
    prefix = tmp_path / "out" / "aday"
    prefix.parent.mkdir()
    existing = _outputs(prefix)[2]
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(SelectionError, match="refusing to overwrite"):
        subtract(Path(manifest["manifest_path"]), drop, prefix)
    existing.unlink()
    decisions = Path(manifest["decisions"]["path"])
    original = decisions.read_bytes()
    decisions.write_bytes(original + b"\0")
    _refused(manifest, drop, prefix, "decisions sha256 differs")
    decisions.write_bytes(original)
    with pytest.raises(SelectionError, match="overwrite an input"):
        subtract(Path(manifest["manifest_path"]), drop, Path(manifest["manifest_path"]).parent / "aday")


def test_post_dedup_drop_refusals_in_rederive(tmp_path: Path) -> None:
    manifest, manifest_object, store_root = _base(tmp_path)
    selection = Path(manifest["selection"]["path"])
    held = _held_out_rows(selection)[0]
    train = _train_lines(selection)
    cases = {
        "held": ([_drop_row(held["doc_id"], 1)], "held-out partition"),
        "line": ([_drop_row(train[2]["doc_id"], 2)], "names candidate line 2"),
        "unused": ([_drop_row("ab" * 32, 1)], "match no train document"),
    }
    for name, (rows, match) in cases.items():
        drop = _write_drops(tmp_path / f"{name}.parquet", rows)
        (tmp_path / name).mkdir()
        with pytest.raises(ValueError, match=match):
            derive_selection_list(
                manifest_object, tmp_path / name / "aday.jsonl", source=None, store_root=store_root,
                run_id=RUN_ID, decided_at=DECIDED_AT, post_dedup_drop_path=drop, **_options(),
            )
        assert not list((tmp_path / name).iterdir()), name


def test_subtract_cli(tmp_path: Path) -> None:
    manifest, _, _ = _base(tmp_path)
    drop = _drops_for(manifest, tmp_path, [4])
    env = dict(os.environ)
    # Ayni paket (kontrol kosularinda scratch kopyasi): CLI de bozulmus kopyayi kosmali.
    env["PYTHONPATH"] = str(Path(selection_module.__file__).resolve().parents[1])
    env["PYTHONIOENCODING"] = "utf-8"
    command = [
        sys.executable, "-m", "derlem_worker.selection", "subtract",
        "--manifest", manifest["manifest_path"], "--drop", str(drop), "--out", str(tmp_path / "cli" / "aday"),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert completed.returncode == 0, completed.stderr
    printed = json.loads(completed.stdout)
    assert printed["subtraction"]["dropped"] == 1
    assert printed["expected_materialization"]["train"]["lines"] == 3
    again = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert again.returncode != 0 and "refusing to overwrite" in again.stderr


def test_clean_candidate_cli_post_dedup_drop_equals_subtract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    from derlem_worker import clean_candidate

    manifest, manifest_object, store_root = _base(tmp_path)
    drop = _drops_for(manifest, tmp_path, [1, 3])
    subtract(Path(manifest["manifest_path"]), drop, tmp_path / "sub" / "aday")
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)  # .env okunmaz
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/never")
    monkeypatch.setattr(sys, "argv", [
        "clean_candidate", "--input-path", str(manifest_object), "--store-root", str(store_root),
        "--output-path", str(tmp_path / "cli" / "aday.jsonl"),
        "--quality-policy", "tr-web-v4", "--held-out-rule", "afacan-held-out-v1", "--near-dedup",
        "--max-document-bytes", "8192", "--selection-list",
        "--run-id", RUN_ID, "--decided-at", DECIDED_AT.isoformat(), "--post-dedup-drop", str(drop),
    ])
    clean_candidate.main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["report"]["removed_post_dedup_drop_lines"] == 2
    assert printed["report"]["post_dedup_drop_sha256"] == hashlib.sha256(drop.read_bytes()).hexdigest()
    sub_selection, sub_decisions, _ = _outputs(tmp_path / "sub" / "aday")
    assert Path(printed["selection"]["path"]).read_bytes() == sub_selection.read_bytes()
    assert Path(printed["decisions"]["path"]).read_bytes() == sub_decisions.read_bytes()
