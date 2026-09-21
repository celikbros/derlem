import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker.clean_candidate_audit import (
    ALLOWED_VERDICTS,
    DROP_DICTIONARY,
    KEEP_DICTIONARY,
    SHEET_COLUMNS,
    STRATUM_ORDER,
    Agreement,
    compute_agreement,
    draw_sheet,
    iter_rejection_records,
    main,
    read_sheet_csv,
    render_score_markdown,
    resolve_dictionary,
    score_sheet,
    wilson_interval,
    write_sheet_csv,
    write_sheet_markdown,
)
from derlem_worker.quality_filters import _REASON_ORDER


def _record(ordinal: int, reasons: list[str], char_count: int, duplicate_of: int | None = None) -> dict:
    record = {
        "char_count": char_count,
        "preview": f"onizleme {ordinal} | boru, \"tirnak\" ve virgul, icerir",
        "reasons": reasons,
        "sha256": hashlib.sha256(f"line-{ordinal}".encode()).hexdigest(),
        "source_ordinal": ordinal,
    }
    if duplicate_of is not None:
        record["duplicate_of"] = duplicate_of
    return record


def _write_report(path: Path, sizes: dict[str, int]) -> None:
    """Her katman icin `sizes[reason]` kayit; ikincil gerekce katmani degistirmez."""
    ordinal = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for reason, size in sizes.items():
            for index in range(size):
                ordinal += 1
                reasons = [reason]
                if index % 3 == 0 and reason != "near_duplicate":
                    reasons.append("commercial_keyword_stuffing")
                duplicate_of = (ordinal - 1) if reason == "near_duplicate" and index % 2 == 0 else None
                handle.write(json.dumps(_record(ordinal, reasons, 100 + index, duplicate_of), ensure_ascii=False) + "\n")


SIZES = {"encoding_corruption": 120, "wiki_markup_residue": 50, "near_duplicate": 7, "language_not_turkish": 3}


def test_stratum_order_is_quality_order_plus_v3_reasons() -> None:
    assert STRATUM_ORDER[: len(_REASON_ORDER)] == tuple(_REASON_ORDER)
    assert STRATUM_ORDER[len(_REASON_ORDER):] == ("near_duplicate", "normalized_duplicate", "language_not_turkish")
    assert len(STRATUM_ORDER) == 15


def test_sheet_row_count_is_sum_of_min_50_and_stratum_size(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, SIZES)

    sheet = draw_sheet(iter_rejection_records(report), seed=7, sheet_size=50, report_path=str(report), report_sha256="x")

    assert len(sheet.rows) == sum(min(50, size) for size in SIZES.values())
    per_stratum: dict[str, int] = {}
    for row in sheet.rows:
        per_stratum[row.stratum] = per_stratum.get(row.stratum, 0) + 1
    assert per_stratum == {reason: min(50, size) for reason, size in SIZES.items()}
    assert {stratum: totals.records for stratum, totals in sheet.stratum_totals.items()} == SIZES
    # Stratum = first reason, secondary reasons do not create a stratum.
    assert "commercial_keyword_stuffing" not in sheet.stratum_totals
    assert [row.stratum for row in sheet.rows] == sorted((row.stratum for row in sheet.rows), key=STRATUM_ORDER.index)
    # Partner preview is filled when the partner ordinal is in the report.
    partners = [row for row in sheet.rows if row.duplicate_of is not None]
    assert partners and all(row.duplicate_of_preview.startswith("onizleme") for row in partners)


def test_same_seed_gives_identical_sheet_sha_and_other_seed_differs(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, SIZES)
    digests = []
    for name, seed in (("a", 11), ("b", 11), ("c", 12)):
        sheet = draw_sheet(
            iter_rejection_records(report), seed=seed, sheet_size=50,
            report_path="report", report_sha256="abc", generated_at="2026-09-19T00:00:00+00:00",
        )
        csv_path = tmp_path / f"{name}.csv"
        write_sheet_csv(sheet, csv_path)
        write_sheet_markdown(sheet, tmp_path / f"{name}.md")
        digests.append(hashlib.sha256(csv_path.read_bytes()).hexdigest())
    assert digests[0] == digests[1]
    assert digests[0] != digests[2]


def test_sheet_csv_round_trips_and_header_carries_provenance(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, SIZES)
    sheet = draw_sheet(iter_rejection_records(report), seed=3, sheet_size=5, report_path=str(report), report_sha256="deadbeef")
    csv_path = tmp_path / "sheet.csv"
    write_sheet_csv(sheet, csv_path)

    text = csv_path.read_text(encoding="utf-8-sig")
    assert "# seed: 3" in text
    assert "# report_sha256: deadbeef" in text
    assert f"# report_path: {report}" in text
    assert "# generated_at: " in text
    assert "# stratum_rule: first reason" in text

    # A blank line an editor may insert between the header and the column row is tolerated.
    original = csv_path.read_bytes()
    csv_path.write_bytes(original.replace(b"\r\nsha256,", b"\r\n\r\nsha256,", 1))
    loaded = read_sheet_csv(csv_path)
    assert loaded.header == sheet.header
    assert loaded.stratum_totals == sheet.stratum_totals
    assert loaded.rows == sheet.rows
    assert all(row.verdict == "" for row in loaded.rows)


def _fill(csv_path: Path, verdict_for_row) -> None:
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for line in lines:
        if line.startswith("#") or line.startswith("sha256,"):
            out.append(line)
            continue
        verdict = verdict_for_row(line)
        out.append(line + verdict)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("\r\n".join(out) + "\r\n")


def test_scorer_reproduces_hand_computed_rate(tmp_path: Path) -> None:
    # Two strata: A has 8000 chars in the report, B has 2000 -> weights 0.8 / 0.2.
    report = tmp_path / "r.rejections.jsonl"
    with report.open("w", encoding="utf-8", newline="\n") as handle:
        for ordinal in range(1, 5):
            handle.write(json.dumps(_record(ordinal, ["encoding_corruption"], 2000)) + "\n")
        for ordinal in range(5, 9):
            handle.write(json.dumps(_record(ordinal, ["near_duplicate"], 500, duplicate_of=1)) + "\n")
    sheet = draw_sheet(iter_rejection_records(report), seed=1, sheet_size=50, report_path="r", report_sha256="s")
    csv_path = tmp_path / "sheet.csv"
    write_sheet_csv(sheet, csv_path)
    # A: good, good, correct_drop, unsure -> p_A = 2/3. B: good, correct_drop, correct_drop, correct_drop -> p_B = 1/4.
    verdicts = iter(["good", "good", "correct_drop", "unsure", "good", "correct_drop", "correct_drop", "correct_drop"])
    _fill(csv_path, lambda line: next(verdicts))

    filled = read_sheet_csv(csv_path)
    result = score_sheet(filled, sheet_path=str(csv_path), sheet_sha256="s", scored_at="2026-09-19T00:00:00+00:00")

    expected = 0.8 * (2 / 3) + 0.2 * (1 / 4)
    assert result.overall_rate == pytest.approx(expected)
    by_reason = {item.reason: item for item in result.strata}
    assert by_reason["encoding_corruption"].rate == pytest.approx(2 / 3)
    assert by_reason["encoding_corruption"].unsure == 1
    assert by_reason["near_duplicate"].rate == pytest.approx(1 / 4)
    assert by_reason["encoding_corruption"].interval == pytest.approx(wilson_interval(2, 3))
    assert by_reason["encoding_corruption"].is_census is False
    # B (near_duplicate) has a 4-record population in the report and all 4 were judged here
    # -> full census: point value, no sampling error, excluded from the n_eff (Kish) sum.
    assert by_reason["near_duplicate"].is_census is True
    assert by_reason["near_duplicate"].interval == pytest.approx((0.25, 0.25))
    assert [item.reason for item in result.top_contributors] == ["encoding_corruption", "near_duplicate"]
    # n_eff = 1 / (0.8^2/3) ; B's term is dropped because it is a full census.
    n_eff = 1 / (0.64 / 3)
    assert result.effective_n == pytest.approx(n_eff)
    assert result.overall_interval == pytest.approx(wilson_interval(expected * n_eff, n_eff))
    assert result.covered_weight == pytest.approx(1.0)
    # Char-weighted within stratum: A good 4000 / judged 6000, B good 500 / judged 2000.
    assert result.overall_char_weighted_rate == pytest.approx(0.8 * (4000 / 6000) + 0.2 * (500 / 2000))

    document = render_score_markdown(result)
    assert "**%58,33**" in document
    assert "`encoding_corruption`" in document
    assert "esigi ile karsilastirma | **ustunde**" in document
    assert "Bayt agirlikli yanlis-atma orani" in document
    assert "TAM SAYIM" in document


def test_wilson_interval_matches_known_value() -> None:
    # 5/50, z = 1.96: centre 0.1285, half-width 0.0851 (textbook Wilson).
    low, high = wilson_interval(5, 50)
    assert (low, high) == pytest.approx((0.0435, 0.2136), abs=1e-3)
    assert wilson_interval(0, 50)[0] == 0.0
    assert wilson_interval(50, 50)[1] == 1.0


def test_scorer_refuses_unknown_verdict(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, {"encoding_corruption": 3})
    sheet = draw_sheet(iter_rejection_records(report), seed=1, sheet_size=50, report_path="r", report_sha256="s")
    csv_path = tmp_path / "sheet.csv"
    write_sheet_csv(sheet, csv_path)
    verdicts = iter(["good", "maybe", "correct_drop"])
    _fill(csv_path, lambda line: next(verdicts))

    with pytest.raises(ValueError, match="unknown verdicts"):
        read_sheet_csv(csv_path)
    with pytest.raises(SystemExit, match="unknown verdicts"):
        main(["score", "--sheet", str(csv_path), "--out", str(tmp_path / "out.md")])
    assert not (tmp_path / "out.md").exists()


def test_scorer_refuses_empty_sheet(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, {"encoding_corruption": 3})
    sheet = draw_sheet(iter_rejection_records(report), seed=1, sheet_size=50, report_path="r", report_sha256="s")
    with pytest.raises(ValueError, match="no verdicts"):
        score_sheet(sheet, sheet_path="x", sheet_sha256="y")


def test_verdicts_are_case_and_space_insensitive_and_agreement_is_computed(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, {"encoding_corruption": 4})
    sheet = draw_sheet(iter_rejection_records(report), seed=1, sheet_size=50, report_path="r", report_sha256="s")
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    write_sheet_csv(sheet, first)
    write_sheet_csv(sheet, second)
    first_verdicts = iter([" Good ", "CORRECT_DROP", "unsure", "good"])
    second_verdicts = iter(["good", "good", "unsure", ""])
    _fill(first, lambda line: next(first_verdicts))
    _fill(second, lambda line: next(second_verdicts))

    loaded_first = read_sheet_csv(first)
    assert [row.verdict for row in loaded_first.rows] == ["good", "correct_drop", "unsure", "good"]
    assert set(ALLOWED_VERDICTS) >= {row.verdict for row in loaded_first.rows}
    agreement = compute_agreement(loaded_first, read_sheet_csv(second))
    assert agreement == Agreement(compared_rows=3, agreeing_rows=2, kappa=pytest.approx(0.5))


def test_cli_sheet_and_score_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "demo.txt.rejections.jsonl"
    _write_report(report, SIZES)
    out_dir = tmp_path / "sheet"
    main(["sheet", "--report", str(report), "--output-dir", str(out_dir), "--seed", "5", "--sheet-size", "2"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["rows"] == 8
    csv_path = Path(summary["csv"])
    assert csv_path.name == "demo_audit_sheet_seed5.csv"
    assert Path(summary["markdown"]).exists()
    assert summary["csv_sha256"] == hashlib.sha256(csv_path.read_bytes()).hexdigest()

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        main(["sheet", "--report", str(report), "--output-dir", str(out_dir), "--seed", "5", "--sheet-size", "2"])

    _fill(csv_path, lambda line: "correct_drop")
    out = tmp_path / "result.md"
    main(["score", "--sheet", str(csv_path), "--out", str(out)])
    summary = json.loads(capsys.readouterr().out)
    assert summary["overall_rate"] == 0.0
    assert out.read_text(encoding="utf-8").count("| `") >= 4


# --- Ters soru (yeni-tutulanlar) sozlugu ---------------------------------------


def _write_raw_sheet(
    path: Path,
    *,
    header_lines: list[str],
    stratum_lines: list[str],
    rows: list[dict[str, str]],
) -> None:
    """Elle ust bilgili bir cetvel yazar (ters sozluk / multi_reason gibi
    `draw_sheet` tarafindan uretilmeyen durumlari test etmek icin)."""
    lines = list(header_lines) + list(stratum_lines)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        for line in lines:
            handle.write(line + "\r\n")
        handle.write(",".join(SHEET_COLUMNS) + "\r\n")
        for row in rows:
            values = [row.get(column, "") for column in SHEET_COLUMNS]
            handle.write(",".join(values) + "\r\n")


def _keep_header_lines(*, stratum_rule: str, report_records: int) -> list[str]:
    return [
        "# version: test-sheet-v1",
        "# seed: 1",
        "# sheet_size: 50",
        "# report_path: r",
        "# report_sha256: s",
        f"# report_records: {report_records}",
        "# generated_at: 2026-09-21T00:00:00+00:00",
        f"# stratum_rule: {stratum_rule}",
        "# allowed_verdicts: garbage / ok_to_keep / unsure",
    ]


def _row(sha: str, reasons: str, char_count: int, ordinal: int, verdict: str) -> dict[str, str]:
    return {
        "sha256": sha,
        "reasons": reasons,
        "char_count": str(char_count),
        "source_ordinal": str(ordinal),
        "preview": "onizleme",
        "duplicate_of": "",
        "duplicate_of_preview": "",
        "verdict": verdict,
    }


def test_score_reads_keep_dictionary_via_header_and_uses_false_keep_terminology(tmp_path: Path) -> None:
    csv_path = tmp_path / "keep.csv"
    header = _keep_header_lines(stratum_rule="first reason in `reasons`", report_records=2)
    stratum_lines = ["# stratum: encoding_corruption records=2 chars=2000"]
    rows = [
        _row("a" * 8, "encoding_corruption", 1000, 1, "ok_to_keep"),
        _row("b" * 8, "encoding_corruption", 1000, 2, "garbage"),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    sheet = read_sheet_csv(csv_path)
    assert sheet.dictionary is KEEP_DICTIONARY
    result = score_sheet(sheet, sheet_path=str(csv_path), sheet_sha256="s", scored_at="2026-09-21T00:00:00+00:00")
    assert result.overall_rate == pytest.approx(0.5)

    document = render_score_markdown(result)
    assert "yanlis-tutma orani" in document
    assert "yanlis-atma orani" not in document
    assert "Yeni-tutulanlar denetimi" in document


def test_dictionary_auto_detected_from_column_content_without_header_field(tmp_path: Path) -> None:
    csv_path = tmp_path / "keep_no_header.csv"
    header = [line for line in _keep_header_lines(stratum_rule="first reason in `reasons`", report_records=2)
              if not line.startswith("# allowed_verdicts")]
    stratum_lines = ["# stratum: encoding_corruption records=2 chars=2000"]
    rows = [
        _row("a" * 8, "encoding_corruption", 1000, 1, "ok_to_keep"),
        _row("b" * 8, "encoding_corruption", 1000, 2, "garbage"),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    sheet = read_sheet_csv(csv_path)
    assert sheet.dictionary is KEEP_DICTIONARY

    # And the drop dictionary is likewise inferred from good/correct_drop content alone.
    resolved = resolve_dictionary(allowed_verdicts_text=None, observed={"good", "correct_drop"}, path=csv_path)
    assert resolved is DROP_DICTIONARY


def test_mixed_verdict_dictionary_is_rejected(tmp_path: Path) -> None:
    csv_path = tmp_path / "mixed.csv"
    header = [line for line in _keep_header_lines(stratum_rule="first reason in `reasons`", report_records=2)
              if not line.startswith("# allowed_verdicts")]
    stratum_lines = ["# stratum: encoding_corruption records=2 chars=2000"]
    rows = [
        _row("a" * 8, "encoding_corruption", 1000, 1, "good"),
        _row("b" * 8, "encoding_corruption", 1000, 2, "garbage"),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    with pytest.raises(ValueError, match="mixed verdict dictionary"):
        read_sheet_csv(csv_path)


def test_dictionary_cannot_be_auto_detected_without_distinguishing_verdicts(tmp_path: Path) -> None:
    csv_path = tmp_path / "ambiguous.csv"
    header = [line for line in _keep_header_lines(stratum_rule="first reason in `reasons`", report_records=2)
              if not line.startswith("# allowed_verdicts")]
    stratum_lines = ["# stratum: encoding_corruption records=2 chars=2000"]
    rows = [
        _row("a" * 8, "encoding_corruption", 1000, 1, "unsure"),
        _row("b" * 8, "encoding_corruption", 1000, 2, ""),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    with pytest.raises(ValueError, match="cannot auto-detect"):
        read_sheet_csv(csv_path)


def test_stratum_rule_without_multi_reason_keeps_first_reason_behaviour(tmp_path: Path) -> None:
    report = tmp_path / "r.rejections.jsonl"
    _write_report(report, {"encoding_corruption": 3})
    sheet = draw_sheet(iter_rejection_records(report), seed=1, sheet_size=50, report_path="r", report_sha256="s")
    csv_path = tmp_path / "sheet.csv"
    write_sheet_csv(sheet, csv_path)
    _fill(csv_path, lambda line: "good")
    loaded = read_sheet_csv(csv_path)
    # draw_sheet's stratum_rule never mentions multi_reason -> today's behaviour survives.
    assert "multi_reason" not in loaded.header.stratum_rule
    assert loaded.multi_reason_mode is False


def test_multi_reason_stratum_and_full_census_exclusion_from_n_eff(tmp_path: Path) -> None:
    """Ters sayfa sekli: `stratum_rule` multi_reason'i belirtir (coklu gerekceli
    satirlar kendi katmanina gider) ve bir tabaka tam sayimdir (n_eff disinda
    kalir, aralik nokta deger)."""
    csv_path = tmp_path / "ters.csv"
    header = _keep_header_lines(
        stratum_rule="first reason in `reasons`; rows with more than one reason form the `multi_reason` stratum",
        report_records=15,
    )
    stratum_lines = [
        "# stratum: reason_a records=2 chars=2000",
        "# stratum: reason_b records=10 chars=6000",
        "# stratum: multi_reason records=3 chars=2000",
    ]
    rows = [
        # reason_a: population 2, both judged here -> full census.
        _row("a1" * 4, "reason_a", 1000, 1, "ok_to_keep"),
        _row("a2" * 4, "reason_a", 1000, 2, "garbage"),
        # reason_b: population 10, only 3 judged here -> not census.
        _row("b1" * 4, "reason_b", 100, 3, "garbage"),
        _row("b2" * 4, "reason_b", 100, 4, "garbage"),
        _row("b3" * 4, "reason_b", 100, 5, "ok_to_keep"),
        # multi_reason: population 3, only 2 judged here -> not census. The
        # first listed reason ("reason_a"/"reason_b") must NOT decide the
        # stratum; both reasons together push the row into `multi_reason`.
        _row("m1" * 4, "reason_a|reason_c", 500, 6, "garbage"),
        _row("m2" * 4, "reason_b|reason_c", 500, 7, "ok_to_keep"),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    sheet = read_sheet_csv(csv_path)
    assert sheet.multi_reason_mode is True
    result = score_sheet(sheet, sheet_path=str(csv_path), sheet_sha256="s", scored_at="2026-09-21T00:00:00+00:00")

    by_reason = {item.reason: item for item in result.strata}
    assert set(by_reason) == {"reason_a", "reason_b", "multi_reason"}
    assert by_reason["multi_reason"].sampled == 2
    assert by_reason["reason_a"].is_census is True
    assert by_reason["reason_a"].interval == pytest.approx((0.5, 0.5))
    assert by_reason["reason_b"].is_census is False
    assert by_reason["multi_reason"].is_census is False

    # Hand-computed: weights 0.2 / 0.6 / 0.2 (2000 / 6000 / 2000 of 10000 chars).
    # rates: a=1/2, b=2/3, multi=1/2.
    expected_rate = 0.2 * 0.5 + 0.6 * (2 / 3) + 0.2 * 0.5
    assert result.overall_rate == pytest.approx(expected_rate)
    assert expected_rate == pytest.approx(0.6)

    # n_eff: reason_a is a full census and is excluded from the Kish sum.
    kish_terms = (0.6 ** 2) / 3 + (0.2 ** 2) / 2
    expected_n_eff = 1 / kish_terms
    assert result.effective_n == pytest.approx(expected_n_eff)
    assert result.overall_interval == pytest.approx(
        wilson_interval(expected_rate * expected_n_eff, expected_n_eff)
    )

    document = render_score_markdown(result)
    assert "TAM SAYIM" in document
    assert "yanlis-tutma orani" in document


def test_full_census_across_all_strata_gives_infinite_n_eff_and_point_interval(tmp_path: Path) -> None:
    csv_path = tmp_path / "all_census.csv"
    header = _keep_header_lines(stratum_rule="first reason in `reasons`", report_records=2)
    stratum_lines = ["# stratum: encoding_corruption records=2 chars=2000"]
    rows = [
        _row("a" * 8, "encoding_corruption", 1000, 1, "ok_to_keep"),
        _row("b" * 8, "encoding_corruption", 1000, 2, "garbage"),
    ]
    _write_raw_sheet(csv_path, header_lines=header, stratum_lines=stratum_lines, rows=rows)

    sheet = read_sheet_csv(csv_path)
    result = score_sheet(sheet, sheet_path=str(csv_path), sheet_sha256="s", scored_at="2026-09-21T00:00:00+00:00")

    assert result.effective_n == float("inf")
    assert result.overall_interval == pytest.approx((0.5, 0.5))
    document = render_score_markdown(result)
    assert "sonsuz" in document
