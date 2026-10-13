"""TASK-049 ek isi: paralel on hesap (``--workers`` / ``--signals-dir``).

Ana iddia: belge-yerel sinyaller (PII, kalite gerekceleri, parmak izi, SimHash,
doc_id) parca satir grubu basina tablolarda, spawn havuzunda hesaplanip sirali
karar gecisine verildiginde secim listesi, karar dosyasi, beklenen metin SHA'lari,
metin kopyasi ve atma raporu tek surecli eski yolla BAYT BAYT aynidir. Tablolar
belirlenimcidir; parca SHA'si ya da politika kimligi degisince reddedilir;
belgeyle tutmayan tablo kosuyu durdurur.

Fikstur ``test_clean_candidate_shards``'inkidir (PII, MT, ticari, birebir ve
yakin kopya, held-out, sinir asimi); burada satir gruplari 2 belgeliktir: 14 belge
-> 3 parca -> 8 tablo, kopya ciftleri tablo sinirlarini asar.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pyarrow.parquet as pq
import pytest

from derlem_worker import clean_candidate_signals as signals_module
from derlem_worker.clean_candidate import derive_clean_candidate, derive_selection_list, selection_artifact_paths
from derlem_worker.clean_candidate_signals import (
    STAGE_OVERSIZED,
    STAGE_PASS,
    SignalTableError,
    signal_table_identity,
    write_signal_table,
)
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V3

from test_clean_candidate_shards import (  # noqa: E402 - ayni fikstur
    DECIDED_AT,
    IZMIR,
    MAX_BYTES,
    RUN_ID,
    _build_store,
    _expected_line,
    _fixture_documents,
    _options,
    _run_cli,
    _write_jsonl,
)

GROUP = 2
TABLES = 8  # parca 5 + 5 + 4 belge, grup 2 -> 3 + 3 + 2


def _store(tmp_path: Path, documents=None):
    return _build_store(tmp_path, documents or _fixture_documents(), row_group_size=GROUP)


def _selection(manifest_object, store_root, out: Path, **kwargs) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    options = {**_options(), **kwargs.pop("options", {})}
    return derive_selection_list(
        manifest_object, out / "aday.jsonl", source=None, store_root=store_root,
        run_id=RUN_ID, decided_at=DECIDED_AT, **options, **kwargs,
    )


def _files(out: Path) -> tuple[bytes, bytes]:
    paths = selection_artifact_paths((out / "aday.jsonl").resolve())
    return paths["selection"].read_bytes(), paths["decisions"].read_bytes()


def _comparable(manifest: dict) -> dict:
    report = {k: v for k, v in manifest["report"].items() if k not in {"generated_at", "signal_precompute"}}
    return {
        "report": report,
        "selection": manifest["selection"]["sha256"],
        "decisions": manifest["decisions"]["sha256"],
        "expected": manifest["expected_materialization"],
        "oversized": manifest["oversized_ordinals"],
        "counts": manifest["decisions"]["counts"],
        "policies": manifest["policies"],
    }


def _table_bytes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.glob("*.parquet"))}


# --------------------------------------------------------------------------
# Esdegerlik
# --------------------------------------------------------------------------


def test_workers_8_equals_workers_1_byte_for_byte(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    serial = _selection(manifest_object, store_root, tmp_path / "w1")
    parallel = _selection(manifest_object, store_root, tmp_path / "w8", workers=8)
    inline = _selection(manifest_object, store_root, tmp_path / "w1s", workers=1, signals_dir=tmp_path / "sig1")

    assert _files(tmp_path / "w8") == _files(tmp_path / "w1") == _files(tmp_path / "w1s")
    assert _comparable(parallel) == _comparable(serial) == _comparable(inline)
    assert serial["report"]["signal_precompute"] is None
    summary = parallel["report"]["signal_precompute"]
    assert summary["workers"] == 8 and summary["tables"] == TABLES and summary["tables_computed"] == TABLES
    assert summary["tables_reused"] == 0 and summary["tables_rejected"] == 0 and summary["documents"] == 14
    assert summary["signals_dir"] is None
    # Gecici tablo dizini kosu sonunda silinir.
    assert not [p for p in (tmp_path / "w8").iterdir() if p.name.startswith("signals.")]
    # Fikstur her karar turunu iceriyor (esdegerlik bos bir seyi sinamiyor).
    assert set(serial["decisions"]["counts"]) >= {
        "pii:reject", "quality_rule:reject", "duplicate:reject", "near_duplicate:reject", "held_out:held_out",
    }
    assert serial["oversized_ordinals"] == [5]


def test_text_copy_and_rejection_report_with_workers_equal_the_serial_copy(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    reports = {}
    for name, extra in (("w1", {}), ("w4", {"workers": 4})):
        (tmp_path / name).mkdir()
        reports[name] = derive_clean_candidate(
            manifest_object, tmp_path / name / "aday.jsonl", source=None, store_root=store_root,
            quality_rejections_path=tmp_path / name / "atilan.jsonl", **_options(), **extra,
        )
    for filename in ("aday.jsonl", "aday_heldout.jsonl", "atilan.jsonl"):
        assert (tmp_path / "w4" / filename).read_bytes() == (tmp_path / "w1" / filename).read_bytes(), filename
    serial, parallel = (
        {k: v for k, v in asdict(reports[n]).items() if k not in {"generated_at", "signal_precompute", "output_path",
                                                                 "held_out_path", "quality_rejections_path"}}
        for n in ("w1", "w4")
    )
    assert serial == parallel and serial["written_lines"] == 4
    assert b"near_duplicate" in (tmp_path / "w4" / "atilan.jsonl").read_bytes()


def test_document_limit_with_workers_equals_the_serial_slice(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    serial = _selection(manifest_object, store_root, tmp_path / "w1", limit_lines=7)
    parallel = _selection(manifest_object, store_root, tmp_path / "w3", limit_lines=7, workers=3)
    assert _files(tmp_path / "w3") == _files(tmp_path / "w1")
    assert _comparable(parallel) == _comparable(serial)
    # Parca 0: gruplar (1-2)(3-4)(5); parca 1: (6-7) -> dilim 4 tablo okur.
    assert parallel["report"]["signal_precompute"]["tables"] == 4
    assert parallel["parent"]["document_limit"] == 7


def test_oversized_boundary_is_the_same_rule_in_the_workers(tmp_path: Path) -> None:
    overhead = len(_expected_line("", None).encode("utf-8"))
    documents = [
        ("a" * (MAX_BYTES - 1 - overhead), None, "train"),
        ("b" * (MAX_BYTES - overhead), None, "oversized"),
        (IZMIR, None, "train"),
    ]
    manifest_object, store_root, _ = _store(tmp_path, documents)
    serial = _selection(manifest_object, store_root, tmp_path / "w1")
    parallel = _selection(manifest_object, store_root, tmp_path / "w2", workers=2)
    assert serial["oversized_ordinals"] == parallel["oversized_ordinals"] == [2]
    assert _files(tmp_path / "w2") == _files(tmp_path / "w1")


# --------------------------------------------------------------------------
# Sinyal tablosu: belirlenimcilik, yeniden kullanim, ret
# --------------------------------------------------------------------------


def test_signal_tables_are_deterministic_whatever_the_worker_count(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    a = _selection(manifest_object, store_root, tmp_path / "a", workers=4, signals_dir=tmp_path / "sig-a")
    b = _selection(manifest_object, store_root, tmp_path / "b", workers=1, signals_dir=tmp_path / "sig-b")
    tables_a, tables_b = _table_bytes(tmp_path / "sig-a"), _table_bytes(tmp_path / "sig-b")
    assert len(tables_a) == TABLES and tables_a == tables_b
    assert a["report"]["signal_precompute"]["tables_sha256"] == b["report"]["signal_precompute"]["tables_sha256"]
    # Ikinci kosu ayni dizine: tablolar ayni bayt (yeniden kullanilir, yeniden yazilmaz).
    c = _selection(manifest_object, store_root, tmp_path / "c", workers=4, signals_dir=tmp_path / "sig-a")
    assert _table_bytes(tmp_path / "sig-a") == tables_a
    assert c["report"]["signal_precompute"]["tables_sha256"] == a["report"]["signal_precompute"]["tables_sha256"]


def test_signal_tables_are_reused_and_a_restart_computes_only_the_missing_ones(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    signals_dir = tmp_path / "sig"
    first = _selection(manifest_object, store_root, tmp_path / "r1", workers=3, signals_dir=signals_dir)
    second = _selection(manifest_object, store_root, tmp_path / "r2", workers=3, signals_dir=signals_dir)
    assert first["report"]["signal_precompute"]["tables_computed"] == TABLES
    summary = second["report"]["signal_precompute"]
    assert summary["tables_reused"] == TABLES and summary["tables_computed"] == 0
    assert summary["signals_dir"] == str(signals_dir.resolve())
    # Yarida kalmis kosu: bir tablo eksik -> yalniz o hesaplanir.
    (signals_dir / "s00001-g0001.parquet").unlink()
    third = _selection(manifest_object, store_root, tmp_path / "r3", workers=3, signals_dir=signals_dir)
    summary = third["report"]["signal_precompute"]
    assert summary["tables_reused"] == TABLES - 1 and summary["tables_computed"] == 1
    assert _files(tmp_path / "r1") == _files(tmp_path / "r2") == _files(tmp_path / "r3")


def test_signal_tables_of_a_changed_shard_are_rejected(tmp_path: Path) -> None:
    documents = _fixture_documents()
    manifest_a, store_a, _ = _store(tmp_path / "a", documents)
    changed = list(documents)
    text, url, expected = changed[13]  # parca 2'nin son belgesi
    changed[13] = (text.replace("liman kentidir", "liman şehridir"), url, expected)
    manifest_b, store_b, _ = _store(tmp_path / "b", changed)
    signals_dir = tmp_path / "sig"
    _selection(manifest_a, store_a, tmp_path / "ra", workers=2, signals_dir=signals_dir)
    rerun = _selection(manifest_b, store_b, tmp_path / "rb", workers=2, signals_dir=signals_dir)
    summary = rerun["report"]["signal_precompute"]
    # Parca 0-1 ayni SHA (6 tablo yeniden kullanilir); parca 2'nin iki tablosu reddedilir.
    assert summary["tables_reused"] == 6 and summary["tables_rejected"] == 2 and summary["tables_computed"] == 2
    fresh = _selection(manifest_b, store_b, tmp_path / "fresh")
    assert _files(tmp_path / "rb") == _files(tmp_path / "fresh")
    assert _comparable(rerun) == _comparable(fresh)
    identity = signal_table_identity(signals_dir / "s00002-g0000.parquet")
    assert identity is not None and identity["shard_sha256"] == rerun["parent"]["shards"][2]["sha256"]


@pytest.mark.parametrize(
    "change",
    ["near_dedup_off", "quality_policy_v3", "max_bytes", "code", "judge"],
)
def test_signal_tables_of_another_policy_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    signals_dir = tmp_path / "sig"
    _selection(manifest_object, store_root, tmp_path / "base", workers=2, signals_dir=signals_dir)
    options: dict = {}
    if change == "near_dedup_off":
        options = {"near_dedup": False}
    elif change == "quality_policy_v3":
        options = {"quality_policy": QUALITY_POLICY_TR_WEB_V3}
    elif change == "max_bytes":
        options = {"max_document_bytes": MAX_BYTES * 2}
    elif change == "code":
        monkeypatch.setattr(signals_module, "signal_code_sha256", lambda: "0" * 64)
    elif change == "judge":
        monkeypatch.setattr(signals_module, "tr_web_v4_judge_id", lambda: "tr-web-v4@000000000000")
    rerun = _selection(
        manifest_object, store_root, tmp_path / "rerun", workers=2, signals_dir=signals_dir, options=options,
    )
    summary = rerun["report"]["signal_precompute"]
    assert summary["tables_rejected"] == TABLES and summary["tables_reused"] == 0
    fresh = _selection(manifest_object, store_root, tmp_path / "fresh", options=options)
    assert _files(tmp_path / "rerun") == _files(tmp_path / "fresh")


@pytest.mark.parametrize("tamper", ["doc_id", "ordinal", "oversized"])
def test_a_signal_table_that_does_not_match_its_documents_stops_the_run(tmp_path: Path, tamper: str) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    signals_dir = tmp_path / "sig"
    _selection(manifest_object, store_root, tmp_path / "base", workers=1, signals_dir=signals_dir)
    # Belge 5 (sinir asimi) parca 0'in ucuncu grubunda tek basina; belge 3-4 ikinci grupta.
    name, index = ("s00000-g0002.parquet", 0) if tamper == "oversized" else ("s00000-g0001.parquet", 1)
    path = signals_dir / name
    identity = signal_table_identity(path)
    rows = [tuple(row.values()) for row in pq.read_table(path).to_pylist()]
    row = list(rows[index])
    if tamper == "doc_id":
        row[2] = bytes(32)
    elif tamper == "ordinal":
        row[0] += 1
    else:
        assert row[1] == STAGE_OVERSIZED
        row[1:] = [STAGE_PASS, bytes(32), [0, 0, 0, 0, 0], [], None, None]
    rows[index] = tuple(row)
    write_signal_table(path, identity, rows)  # kimlik ayni: yeniden kullanilir, dongu yakalar
    with pytest.raises(SignalTableError):
        _selection(manifest_object, store_root, tmp_path / "rerun", workers=1, signals_dir=signals_dir)
    paths = selection_artifact_paths((tmp_path / "rerun" / "aday.jsonl").resolve())
    assert not paths["selection"].exists() and not paths["decisions"].exists()


# --------------------------------------------------------------------------
# Korumalar
# --------------------------------------------------------------------------


def test_parallel_pre_compute_needs_an_import_manifest(tmp_path: Path) -> None:
    jsonl = _write_jsonl(tmp_path / "belgeler.jsonl", _fixture_documents())
    with pytest.raises(ValueError, match="import-manifest"):
        derive_selection_list(jsonl, tmp_path / "a" / "aday.jsonl", source=None, workers=2, **_options())
    with pytest.raises(ValueError, match="import-manifest"):
        derive_clean_candidate(
            jsonl, tmp_path / "b" / "aday.jsonl", source=None, signals_dir=tmp_path / "sig", **_options(),
        )
    with pytest.raises(ValueError, match="workers"):
        derive_clean_candidate(jsonl, tmp_path / "c" / "aday.jsonl", source=None, workers=0, **_options())


def test_signal_module_imports_no_database_config_or_worker_entry_point() -> None:
    # Spawn iscisi bu modulu import eder: veritabani, yapilandirma, worker giris noktasi YOK.
    code = (
        "import sys, json; import derlem_worker.clean_candidate_signals; "
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith(('derlem_worker', 'psycopg')))))"
    )
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120, check=True,
    )
    modules = set(json.loads(result.stdout))
    assert "derlem_worker.clean_candidate_signals" in modules
    forbidden = {"derlem_worker.__main__", "derlem_worker.main", "derlem_worker.config", "derlem_worker.clean_candidate"}
    assert not modules & forbidden, modules & forbidden
    assert not [m for m in modules if m.startswith("psycopg")]


def test_command_line_workers_and_signals_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    manifest_object, store_root, _ = _store(tmp_path)
    jsonl = _write_jsonl(tmp_path / "belgeler.jsonl", _fixture_documents())
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)  # .env okunmaz
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/never")
    common = [
        "--quality-policy", "tr-web-v4", "--held-out-rule", "afacan-held-out-v1", "--near-dedup",
        "--max-document-bytes", str(MAX_BYTES), "--selection-list",
        "--run-id", RUN_ID, "--decided-at", "2026-10-13T12:00:00+00:00",
    ]
    source = ["--input-path", str(manifest_object), "--store-root", str(store_root)]
    serial = _run_cli(monkeypatch, capsys, [*source, "--output-path", str(tmp_path / "a" / "aday.jsonl"), *common])
    parallel = _run_cli(monkeypatch, capsys, [
        *source, "--output-path", str(tmp_path / "b" / "aday.jsonl"), *common,
        "--workers", "3", "--signals-dir", str(tmp_path / "sig"),
    ])
    assert parallel["selection"]["sha256"] == serial["selection"]["sha256"]
    assert parallel["decisions"]["sha256"] == serial["decisions"]["sha256"]
    assert parallel["expected_materialization"] == serial["expected_materialization"]
    assert parallel["report"]["signal_precompute"]["workers"] == 3
    assert len(list((tmp_path / "sig").glob("*.parquet"))) == TABLES

    with pytest.raises(SystemExit):  # satir kaynaginda paralel on hesap yok
        _run_cli(monkeypatch, capsys, [
            "--input-path", str(jsonl), "--output-path", str(tmp_path / "c" / "aday.jsonl"), *common,
            "--workers", "2",
        ])
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, capsys, [*source, "--output-path", str(tmp_path / "d" / "aday.jsonl"), *common,
                                       "--workers", "0"])
