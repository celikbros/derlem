"""TASK-049: clean_candidate parcali kaynaktan (derlem.import-manifest.v1).

Ana iddia: parca okuyucusu = satir okuyucusu. Ayni belgeler aday satiri bicimiyle
(``{"text", "url"}``, sirali anahtar, kompakt JSON) bir JSONL dosyasina yazilip
satir satir okununca secim listesi, karar dosyasi, beklenen metin SHA'lari ve sinir
asimi listesi bayt bayt ayni cikar; parcalardan materialize edilen metin, satir
yolunun metin kopyasiyla bayt bayt aynidir.

Beklenen satir bicimi bu dosyada BAGIMSIZ yazilir (``_expected_line``):
``candidate_line`` degisirse iki yol birlikte kaymaz, test kirmiziya doner.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

import pytest

from derlem_worker import machine_translation as mt
from derlem_worker.clean_candidate import (
    HELD_OUT_RULE_AFACAN_V1,
    _is_held_out_hex,
    derive_clean_candidate,
    derive_selection_list,
    selection_artifact_paths,
)
from derlem_worker.document_record import (
    DocumentRecordError,
    make_document,
    publish_parquet,
    read_decisions,
    read_selection,
    write_document_shards,
)
from derlem_worker.import_manifest import (
    CANDIDATE_LINE_FORMAT,
    IMPORT_MANIFEST_SCHEMA,
    ImportManifestError,
    candidate_line,
    load_import_manifest,
    manifest_candidate_lines,
    storage_key_for,
)
from derlem_worker.quality_filters import QUALITY_POLICY_TR_WEB_V4, quality_rejection_reasons
from derlem_worker.selection import SelectionError, materialize
from derlem_worker.similarity import document_simhash, hamming_distance
from derlem_worker.storage import ContentAddressedStore

MAX_BYTES = 8192
RUN_ID = "task-049-test"
DECIDED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

# Gercek veriden: bu uuid'nin rakam gruplari telefon desenine uyuyor. Kimlik satira
# girseydi PII kapisi belgeyi atardi (aday satirinda kimlik yok).
PII_LOOKING_UUID = "<urn:uuid:1fdc5126-5943-4899-93ed-6c995a815004>"

_NEUTRAL = (
    "kalem masa duvar pencere kapı bahçe ağaç yaprak çiçek toprak deniz kum taş "
    "yol köprü şehir köy dağ nehir göl orman bulut yağmur rüzgâr güneş ay yıldız "
    "kitap defter okul sınıf öğretmen öğrenci araba otobüs tren uçak gemi liman"
).split()


def _prose(total: int, *, calque: int = 0, per_sentence: int = 10, shift: int = 0) -> str:
    calques = sorted(mt.CALQUE_WORDS)
    words = [calques[i % len(calques)] for i in range(calque)]
    words += [_NEUTRAL[(i + shift) % len(_NEUTRAL)] for i in range(total - calque)]
    sentences = [" ".join(words[i : i + per_sentence]) for i in range(0, len(words), per_sentence)]
    return " ".join(s[:1].upper() + s[1:] + "." for s in sentences)


ANKARA = (
    "Ankara, Türkiye'nin başkenti ve en kalabalık ikinci şehridir.\n\n"
    "1923 yılında başkent ilan edilen şehrin nüfusu 2020 sayımına göre 5.663.322 kişidir.\n"
    "Şehir, İç Anadolu Bölgesi'nde yer alır ve tarih boyunca Galatlar, Romalılar ve "
    "Selçuklular tarafından yönetilmiştir."
)
IZMIR = (
    "İzmir, Ege Denizi kıyısında kurulmuş bir liman kentidir ve Türkiye'nin üçüncü büyük şehridir.\n"
    "Körfezin çevresine yayılan kentte antik çağdan kalma Smyrna agorası ziyaretçilere açıktır.\n\n"
    "Kordon boyunca yürüyüş yolu ve tarihi asansör, şehrin en çok bilinen yerleri arasındadır."
)
NEAR_BASE = (
    "Karadeniz kıyısındaki küçük kasabada sabahları balıkçılar limana döner, kahvehaneler dolar "
    "ve pazar yerinde taze hamsi satılır. Yaz aylarında yaylalara çıkan aileler çay bahçelerinde "
    "dinlenir, akşamları ise sahil yolunda yürüyüş yapılır. Kasabanın eski camisi on dokuzuncu "
    "yüzyılda yapılmış olup ahşap işçiliğiyle tanınır ve her yıl pek çok ziyaretçi ağırlar. "
    "Belediye geçen yıl eski çarşıyı onarmış, dar sokaklara yeni taş döşemiştir."
)
NEAR_VARIANT = NEAR_BASE.replace("her yıl", "her sene")
COMMERCIAL = ANKARA.replace("\n\n", " ") + " Bilet 49,90 TL. Hemen sipariş verin, ücretsiz kargo."
URL_MT = _prose(400, shift=3)
STRONG_MT = _prose(400, calque=20, shift=5)


def _held_out_text() -> str:
    for index in range(400_000):
        text = f"Bu satır held-out kuralını sağlayan sıradan bir Türkçe cümledir, sıra {index}."
        if _is_held_out_hex(hashlib.sha256(_expected_line(text, None).encode("utf-8")).hexdigest()):
            return text
    raise AssertionError("no held-out text found")


def _expected_line(text: str, url: str | None) -> str:
    return json.dumps({"text": text, "url": url}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _fixture_documents() -> list[tuple[str, str | None, str]]:
    """(metin, url, beklenen karar) -- parca sinirlarini asacak kadar belge."""
    return [
        (ANKARA, "https://tr.wikipedia.org/wiki/Ankara", "train"),
        ("Yazara ulasmak icin test@example.com adresine yazabilirsiniz, diye not dusulmus.", None, "pii"),
        ("Bilgi hattı 0532\n1234567 numarasıdır; metinde iki satıra bölünmüş.", None, "pii"),
        (IZMIR, "http://kisi@ornek.org/izmir", "pii"),
        ("oversized " + "x" * 9000, "https://example.com/buyuk", "oversized"),
        (URL_MT, "https://tr.topwar.ru/1.html", "quality_rule"),
        (URL_MT + " Ek.", "https://example.com/makale", "train"),
        (STRONG_MT, None, "quality_rule"),
        (COMMERCIAL, "https://example.com/bilet", "quality_rule"),
        (ANKARA, "https://ornek.com.tr/ankara", "duplicate"),
        (NEAR_BASE, "https://example.com/kasaba", "train"),
        (_held_out_text(), None, "held_out"),
        (NEAR_VARIANT, "https://example.com/kasaba-2", "near_duplicate"),
        (IZMIR, "https://example.com/izmir", "train"),
    ]


def _build_store(tmp_path: Path, documents, *, rows_per_shard: int = 5) -> tuple[Path, Path, list[dict]]:
    records = [
        make_document(
            text=text,
            source_ordinal=index,
            source_id="fixture-source",
            provenance={"url": url, "external_id": PII_LOOKING_UUID if index == 1 else f"<urn:uuid:{index:08x}>"},
            language={"declared": "tr"},
        )
        for index, (text, url, _) in enumerate(documents, 1)
    ]
    shards = write_document_shards(records, tmp_path / "shards", rows_per_shard=rows_per_shard)
    store = ContentAddressedStore(tmp_path / "store")
    for info in shards:
        publish_parquet(store, info)
    manifest = {
        "schema": IMPORT_MANIFEST_SCHEMA,
        "dataset": "test/fixture",
        "revision": "0" * 40,
        "config": "tur_Latn",
        "shards": [
            {
                "file": f"part-{index}.parquet",
                "sha256": info.sha256,
                "byte_size": info.byte_size,
                "row_count": info.row_count,
                "first_source_ordinal": info.first_source_ordinal,
                "last_source_ordinal": info.last_source_ordinal,
            }
            for index, info in enumerate(shards)
        ],
        "totals": {"documents": len(records), "text_utf8_bytes": sum(len(r["text"].encode()) for r in records)},
    }
    stored = store.ingest_bytes(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    return store.root / stored.storage_key, store.root, records


def _write_jsonl(path: Path, documents) -> Path:
    path.write_bytes(b"".join((_expected_line(text, url) + "\n").encode("utf-8") for text, url, _ in documents))
    return path


def _options() -> dict:
    return dict(
        max_document_bytes=MAX_BYTES,
        quality_policy=QUALITY_POLICY_TR_WEB_V4,
        held_out_rule=HELD_OUT_RULE_AFACAN_V1,
        near_dedup=True,
    )


def _decision_kinds(decisions_path: Path) -> dict[int, str]:
    kinds: dict[int, str] = {}
    for row in read_decisions(decisions_path):
        kinds.setdefault(int(row["source_ordinal"]), row["decision_type"])
    return kinds


# --------------------------------------------------------------------------
# Fikstur kendisi (yoksa esdegerlik testi yanlis seyi sinar)
# --------------------------------------------------------------------------


def test_fixture_cases_are_what_they_claim() -> None:
    documents = _fixture_documents()
    for text, url, expected in documents:
        reasons = quality_rejection_reasons(text.strip(), QUALITY_POLICY_TR_WEB_V4, url=url)
        if expected == "quality_rule":
            assert reasons, text[:40]
        elif expected in {"train", "held_out", "duplicate", "near_duplicate"}:
            assert not reasons, (text[:40], reasons)
    signature = document_simhash(NEAR_BASE)
    variant = document_simhash(NEAR_VARIANT)
    assert signature is not None and variant is not None and 0 < hamming_distance(signature, variant) <= 3
    # URL'nin karara girdigi tek belge: ayni metin URL imzasiyla ceviri, imzasiz tutulur.
    assert quality_rejection_reasons(URL_MT, QUALITY_POLICY_TR_WEB_V4, url="https://tr.topwar.ru/1.html")
    assert not quality_rejection_reasons(URL_MT, QUALITY_POLICY_TR_WEB_V4, url=None)


def test_candidate_line_is_the_documented_format() -> None:
    document = make_document(
        text="Satır bir.\n\nİkinci \"paragraf\".", source_ordinal=1,
        provenance={"url": "https://örnek.com.tr/a", "external_id": PII_LOOKING_UUID},
    )
    line = candidate_line(document)
    assert line == '{"text":"Satır bir.\\n\\nİkinci \\"paragraf\\".","url":"https://örnek.com.tr/a"}'
    assert line == _expected_line(document["text"], "https://örnek.com.tr/a")
    assert json.loads(line)["text"] == document["text"]  # metin degismez
    assert "uuid" not in line and CANDIDATE_LINE_FORMAT == "derlem.candidate-line.v1"


def test_a_shard_cannot_hold_an_empty_document() -> None:
    # Bos belge parcaya hic girmez (uyarlayici sayar): parca yolunda empty_text karari dogmaz.
    with pytest.raises(DocumentRecordError, match="empty"):
        make_document(text="  \n\t ", source_ordinal=1)


# --------------------------------------------------------------------------
# Esdegerlik: parca okuyucusu = satir okuyucusu
# --------------------------------------------------------------------------


def test_shard_reader_equals_line_reader_byte_for_byte(tmp_path: Path) -> None:
    documents = _fixture_documents()
    manifest_object, store_root, _ = _build_store(tmp_path, documents)
    jsonl = _write_jsonl(tmp_path / "ayni-belgeler.jsonl", documents)
    (tmp_path / "parca").mkdir()
    (tmp_path / "satir").mkdir()

    shard = derive_selection_list(
        manifest_object, tmp_path / "parca" / "aday.jsonl", source=None, store_root=store_root,
        run_id=RUN_ID, decided_at=DECIDED_AT, **_options(),
    )
    line = derive_selection_list(
        jsonl, tmp_path / "satir" / "aday.jsonl", source=None, run_id=RUN_ID, decided_at=DECIDED_AT, **_options(),
    )

    shard_files = selection_artifact_paths((tmp_path / "parca" / "aday.jsonl").resolve())
    line_files = selection_artifact_paths((tmp_path / "satir" / "aday.jsonl").resolve())
    assert shard_files["selection"].read_bytes() == line_files["selection"].read_bytes()
    assert shard_files["decisions"].read_bytes() == line_files["decisions"].read_bytes()
    assert shard["expected_materialization"] == line["expected_materialization"]
    assert shard["oversized_ordinals"] == line["oversized_ordinals"] == [5]
    assert shard["decisions"]["counts"] == line["decisions"]["counts"]

    # Her belge beklenen yoldan gecti (fikstur iddiasi karar dosyasinda).
    kinds = _decision_kinds(shard_files["decisions"])
    selected = {int(row["source_ordinal"]): row["partition"] for row in read_selection(shard_files["selection"])}
    for ordinal, (_, _, expected) in enumerate(documents, 1):
        if expected == "oversized":
            assert ordinal in shard["oversized_ordinals"]
        elif expected == "train":
            assert selected.get(ordinal) == "train" and ordinal not in kinds, ordinal
        elif expected == "held_out":
            assert selected.get(ordinal) == "held_out" and kinds[ordinal] == "held_out"
        else:
            assert kinds.get(ordinal) == expected and ordinal not in selected, (ordinal, kinds.get(ordinal))

    # Manifest: kaynak manifest SHA'si, parca listesi, politika kimlikleri, yorumlayici/zlib.
    parent = shard["parent"]
    assert parent["kind"] == "import_manifest" and parent["line_format"] == CANDIDATE_LINE_FORMAT
    assert parent["sha256"] == hashlib.sha256(manifest_object.read_bytes()).hexdigest()
    assert [entry["index"] for entry in parent["shards"]] == [0, 1, 2]
    assert shard["report"]["quality_judge"].startswith("tr-web-v4@")
    assert shard["report"]["machine_translation_target"] == mt.MT_TARGET
    assert shard["report"]["interpreter_version"] and shard["report"]["zlib_runtime_version"]
    assert shard["policies"]["near_duplicate"] == "normalized-word-3gram-simhash64-v1-hamming3"
    assert shard["policies"]["held_out"] == HELD_OUT_RULE_AFACAN_V1
    judges = {row["judge"] for row in read_decisions(shard_files["decisions"]) if row["decision_type"] == "quality_rule"}
    assert judges == {shard["report"]["quality_judge"]}
    assert "test@example.com" not in json.dumps(shard) and "1234567" not in json.dumps(shard)


def test_text_copy_from_shards_equals_line_text_copy_and_materialize(tmp_path: Path) -> None:
    documents = _fixture_documents()
    manifest_object, store_root, _ = _build_store(tmp_path, documents)
    jsonl = _write_jsonl(tmp_path / "ayni-belgeler.jsonl", documents)
    for name in ("satir", "parca", "liste", "m1", "m2"):
        (tmp_path / name).mkdir()

    line_copy = derive_clean_candidate(jsonl, tmp_path / "satir" / "aday.jsonl", source=None, **_options())
    shard_copy = derive_clean_candidate(
        manifest_object, tmp_path / "parca" / "aday.jsonl", source=None, store_root=store_root, **_options(),
    )
    assert (tmp_path / "parca" / "aday.jsonl").read_bytes() == (tmp_path / "satir" / "aday.jsonl").read_bytes()
    assert (tmp_path / "parca" / "aday_heldout.jsonl").read_bytes() == (tmp_path / "satir" / "aday_heldout.jsonl").read_bytes()
    assert shard_copy.output_sha256 == line_copy.output_sha256 and shard_copy.written_lines == 4
    assert shard_copy.held_out_lines == 1 and shard_copy.input_kind == "import_manifest"
    assert line_copy.input_kind is None and line_copy.import_manifest is None

    manifest = derive_selection_list(
        manifest_object, tmp_path / "liste" / "aday.jsonl", source=None, store_root=store_root, **_options(),
    )
    results = []
    for name in ("m1", "m2"):
        results.append(materialize(
            Path(manifest["manifest_path"]), output_path=tmp_path / name / "aday.jsonl",
            held_out_output_path=tmp_path / name / "aday_heldout.jsonl", verify_parent=True,
        ))
        assert (tmp_path / name / "aday.jsonl").read_bytes() == (tmp_path / "satir" / "aday.jsonl").read_bytes()
        assert (tmp_path / name / "aday_heldout.jsonl").read_bytes() == (tmp_path / "satir" / "aday_heldout.jsonl").read_bytes()
    assert results[0]["outputs"] == results[1]["outputs"]
    assert results[0]["method"] == "import-manifest-candidate-lines-by-ordinal-sha256-verified-v1"
    # Paragraf sonlari aday satirinda kacisli durur ve geri okununca metin aynidir.
    first = json.loads((tmp_path / "m1" / "aday.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first == {"text": ANKARA, "url": "https://tr.wikipedia.org/wiki/Ankara"}


def test_selection_and_decisions_are_deterministic_across_runs(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _build_store(tmp_path, _fixture_documents())
    shas = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        manifest = derive_selection_list(
            manifest_object, tmp_path / name / "aday.jsonl", source=None, store_root=store_root,
            run_id=RUN_ID, decided_at=DECIDED_AT, **_options(),
        )
        shas.append((manifest["selection"]["sha256"], manifest["decisions"]["sha256"],
                     manifest["expected_materialization"]))
    assert shas[0] == shas[1]


# --------------------------------------------------------------------------
# Korumalar
# --------------------------------------------------------------------------


def test_import_manifest_without_store_root_is_refused(tmp_path: Path) -> None:
    manifest_object, _, _ = _build_store(tmp_path, _fixture_documents()[:3])
    with pytest.raises(ValueError, match="store_root"):
        derive_clean_candidate(manifest_object, tmp_path / "aday.jsonl", source=None, **_options())
    assert not (tmp_path / "aday.jsonl").exists()


def test_oversized_boundary_counts_the_line_with_its_lf(tmp_path: Path) -> None:
    def text_for(line_bytes: int) -> str:
        overhead = len(_expected_line("", None).encode("utf-8"))
        return "a" * (line_bytes - overhead)

    documents = [(text_for(MAX_BYTES - 1), None, "train"), (text_for(MAX_BYTES), None, "oversized")]
    manifest_object, store_root, _ = _build_store(tmp_path, documents)
    rows = list(manifest_candidate_lines(load_import_manifest(manifest_object), store_root, MAX_BYTES))
    assert [(ordinal, oversized) for ordinal, _, oversized in rows] == [(1, False), (2, True)]
    assert len(rows[0][1].encode("utf-8")) + 1 == MAX_BYTES


def test_document_limit_reads_a_prefix_and_lists_only_the_shards_it_read(tmp_path: Path) -> None:
    documents = _fixture_documents()
    manifest_object, store_root, _ = _build_store(tmp_path, documents)
    manifest = derive_selection_list(
        manifest_object, tmp_path / "aday.jsonl", source=None, store_root=store_root, limit_lines=7, **_options(),
    )
    assert manifest["report"]["total_lines"] == 7 and manifest["parent"]["document_limit"] == 7
    assert [entry["index"] for entry in manifest["parent"]["shards"]] == [0, 1]
    assert manifest["parent"]["last_source_ordinal"] == 7
    result = materialize(Path(manifest["manifest_path"]))
    assert result["outputs"]["train"]["sha256"] == manifest["expected_materialization"]["train"]["sha256"]


def test_materialize_refuses_a_tampered_shard(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _build_store(tmp_path, _fixture_documents())
    manifest = derive_selection_list(
        manifest_object, tmp_path / "aday.jsonl", source=None, store_root=store_root, **_options(),
    )
    shard_sha = manifest["parent"]["shards"][0]["sha256"]
    shard_path = store_root / storage_key_for(shard_sha)
    shard_path.chmod(0o644)
    data = bytearray(shard_path.read_bytes())
    data[200] ^= 0xFF
    shard_path.write_bytes(bytes(data))
    out = tmp_path / "out.jsonl"
    with pytest.raises(ImportManifestError, match="does not match"):
        materialize(Path(manifest["manifest_path"]), output_path=out)
    assert not out.exists()


def test_materialize_refuses_a_shard_list_that_differs_from_the_import_manifest(tmp_path: Path) -> None:
    manifest_object, store_root, _ = _build_store(tmp_path, _fixture_documents())
    manifest = derive_selection_list(
        manifest_object, tmp_path / "aday.jsonl", source=None, store_root=store_root, **_options(),
    )
    path = Path(manifest["manifest_path"])
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["parent"]["shards"][1]["sha256"] = "f" * 64
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(SelectionError, match="shards differ"):
        materialize(path)
    stored["parent"]["shards"][1]["sha256"] = manifest["parent"]["shards"][1]["sha256"]
    stored["parent"]["line_format"] = "derlem.candidate-line.v0"
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(SelectionError, match="line format"):
        materialize(path)


def test_materialize_refuses_a_selection_whose_doc_id_is_not_the_candidate_line(tmp_path: Path) -> None:
    # Ayni belgelerin BASKA bicimli satiri (ornegin kimlik eklenmis) baska doc_id verir.
    documents = _fixture_documents()
    manifest_object, store_root, records = _build_store(tmp_path, documents)
    other = tmp_path / "id-li.jsonl"
    other.write_bytes(b"".join(
        (json.dumps({"id": r["provenance"]["external_id"], "text": r["text"], "url": r["provenance"]["url"]},
                    ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        for r in records
    ))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    shard = derive_selection_list(
        manifest_object, tmp_path / "a" / "aday.jsonl", source=None, store_root=store_root, **_options(),
    )
    foreign = derive_selection_list(other, tmp_path / "b" / "aday.jsonl", source=None, **_options())
    path = Path(shard["manifest_path"])
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["selection"]["path"] = foreign["selection"]["path"]
    stored["selection"]["sha256"] = foreign["selection"]["sha256"]
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(SelectionError, match="does not match its doc_id"):
        materialize(path)


def test_pii_in_text_split_by_a_line_break_is_caught_for_json_lines_only(tmp_path: Path) -> None:
    # JSON satirinda "\\n" kacisli: satir taramasi numarayi gormez, metin taramasi gorur.
    # Duz metin satirinda satir = metin; davranis eskisiyle ayni.
    split = "Bilgi hattı 0532\n1234567 numarasıdır; metinde iki satıra bölünmüş."
    jsonl = tmp_path / "a.jsonl"
    jsonl.write_bytes((_expected_line(split, None) + "\n").encode("utf-8"))
    report = derive_clean_candidate(jsonl, tmp_path / "a-aday.jsonl", source=None, max_document_bytes=MAX_BYTES)
    assert report.removed_pii_lines == 1 and report.pii_line_counts["phone"] == 1
    assert report.pii_findings["phone"] == 1  # iki gorunumun buyugu, toplami degil
    plain = tmp_path / "b.txt"
    plain.write_bytes("Bilgi hattı 0532 1234567 numarasıdır.\nTemiz ikinci satır burada durur.\n".encode("utf-8"))
    report = derive_clean_candidate(plain, tmp_path / "b-aday.txt", source=None, max_document_bytes=MAX_BYTES)
    # Duz metin satiri: satir = metin, tek tarama; sayac iki kez sayilmaz.
    assert report.removed_pii_lines == 1 and report.pii_findings["phone"] == 1 and report.written_lines == 1


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, argv: list[str]) -> dict:
    from derlem_worker import clean_candidate

    monkeypatch.setattr(sys, "argv", ["clean_candidate", *argv])
    clean_candidate.main()
    return json.loads(capsys.readouterr().out)


def test_command_line_shard_selection_is_reproducible_and_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    manifest_object, store_root, _ = _build_store(tmp_path, _fixture_documents())
    jsonl = _write_jsonl(tmp_path / "ayni-belgeler.jsonl", _fixture_documents())
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)  # .env okunmaz
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/never")
    common = [
        "--quality-policy", "tr-web-v4", "--held-out-rule", "afacan-held-out-v1", "--near-dedup",
        "--max-document-bytes", str(MAX_BYTES), "--selection-list",
        "--run-id", RUN_ID, "--decided-at", "2026-10-13T12:00:00+00:00",
    ]
    results = []
    for name in ("a", "b"):
        results.append(_run_cli(monkeypatch, capsys, [
            "--input-path", str(manifest_object), "--store-root", str(store_root),
            "--output-path", str(tmp_path / name / "aday.jsonl"), "--limit-lines", "9", *common,
        ]))
    assert results[0]["selection"]["sha256"] == results[1]["selection"]["sha256"]
    assert results[0]["decisions"]["sha256"] == results[1]["decisions"]["sha256"]
    assert results[0]["parent"]["document_limit"] == 9 and results[0]["report"]["total_lines"] == 9
    decided = {row["decided_at"] for row in read_decisions(Path(results[0]["decisions"]["path"]))}
    assert decided == {DECIDED_AT}

    with pytest.raises(SystemExit):  # parcali girdi depo koku ister
        _run_cli(monkeypatch, capsys, [
            "--input-path", str(manifest_object), "--output-path", str(tmp_path / "c" / "aday.jsonl"), *common,
        ])
    with pytest.raises(SystemExit):  # satir kaynaginda secim listesi dilimlenmez (eski kural)
        _run_cli(monkeypatch, capsys, [
            "--input-path", str(jsonl), "--output-path", str(tmp_path / "d" / "aday.jsonl"), "--limit-lines", "9", *common,
        ])
    with pytest.raises(SystemExit):  # saat dilimsiz karar zamani reddedilir
        _run_cli(monkeypatch, capsys, [
            "--input-path", str(manifest_object), "--store-root", str(store_root),
            "--output-path", str(tmp_path / "e" / "aday.jsonl"), *common[:-1], "2026-10-13T12:00:00",
        ])
