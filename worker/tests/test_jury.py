"""TASK-047: hakem orneklemesi -- orneklem, kor dosya, kilavuz SHA, karar satirlari,
dort sayi, butce, anahtarsiz yol, kurucu capasi (veritabanisiz)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from derlem_worker import jury
from derlem_worker.document_record import make_document, publish_parquet, read_decisions, write_document_shards
from derlem_worker.import_manifest import IMPORT_MANIFEST_SCHEMA
from derlem_worker.jury import (
    BLIND_FIELDS,
    BudgetLedger,
    BudgetLimits,
    JudgeResponse,
    JudgeSettings,
    JuryBudget,
    JuryBudgetExhausted,
    JuryError,
)
from derlem_worker.jury_scoring import (
    Verdict,
    VerdictFileError,
    agreement_report,
    choose_anchor_rows,
    cohen_kappa,
    junk_numbers,
    load_verdict_file,
    parse_anchor_sheet,
    render_anchor_sheet,
    wilson,
)
from derlem_worker.storage import ContentAddressedStore

# Kilavuz SHA sabitlemesi: kilavuz metni degisirse bu test kirmizi olur ve
# hakem kimligi (judge id) bilincli olarak yeni surume tasinir (juri-siki-v2).
PINNED_RUBRIC_SHA256 = "50e993d6f5fe5308e7914b6cd4d0981b62151aa4d0d156b3a4c78c7409800bbe"
DECIDED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _texts(count: int) -> list[str]:
    return [
        f"Belge {index} başlık\n\nBirinci paragraf {index} burada.\tİkinci  satır   {index * 7}.\n"
        for index in range(1, count + 1)
    ]


def _manifest_source(tmp_path: Path, texts: list[str], *, rows_per_shard: int = 7, row_group_size: int = 3,
                     name: str = "m") -> tuple[Path, Path]:
    documents = [
        make_document(
            text=text,
            source_ordinal=index,
            provenance={"dataset": "epfml/FineWeb2-HQ", "url": f"https://site{index}.example/yol/{index}",
                        "dump": "CC-MAIN-2024-10", "external_id": f"<urn:uuid:kimlik-{index}>"},
            signals={"quality_score": 0.5 + index / 1000},
        )
        for index, text in enumerate(texts, 1)
    ]
    store_root = tmp_path / f"store-{name}"
    store = ContentAddressedStore(store_root)
    shards = write_document_shards(documents, tmp_path / f"shards-{name}", rows_per_shard=rows_per_shard,
                                   row_group_size=row_group_size)
    entries = []
    for shard in shards:
        publish_parquet(store, shard)
        entries.append({"sha256": shard.sha256, "byte_size": shard.byte_size, "row_count": shard.row_count,
                        "first_source_ordinal": shard.first_source_ordinal, "last_source_ordinal": shard.last_source_ordinal})
    manifest = {"schema": IMPORT_MANIFEST_SCHEMA, "shards": entries,
                "totals": {"documents": len(texts), "text_utf8_bytes": sum(len(t.encode()) for t in texts)}}
    manifest_path = tmp_path / f"manifest-{name}.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, store_root


def _prepared_run(tmp_path: Path, count: int = 12, n: int = 10) -> tuple[Path, jury.SampleDraw]:
    manifest_path, store_root = _manifest_source(tmp_path, _texts(count))
    draw = jury.draw_sample(manifest_path, n=n, seed=7, store_root=store_root)
    run_dir = tmp_path / "run"
    jury.prepare_run(draw, run_dir, source_id="11111111-2222-3333-4444-555555555555", object_sha256="a" * 64,
                     created_at=DECIDED_AT)
    return run_dir, draw


def _write_verdicts(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ orneklem


def test_manifest_sampling_is_deterministic_and_independent_of_shard_layout(tmp_path: Path) -> None:
    texts = _texts(40)
    path_a, store_a = _manifest_source(tmp_path, texts, rows_per_shard=7, row_group_size=3, name="a")
    path_b, store_b = _manifest_source(tmp_path, texts, rows_per_shard=40, row_group_size=40, name="b")

    first = jury.draw_sample(path_a, n=10, seed=20261013, store_root=store_a)
    again = jury.draw_sample(path_a, n=10, seed=20261013, store_root=store_a)
    relaid = jury.draw_sample(path_b, n=10, seed=20261013, store_root=store_b)
    other_seed = jury.draw_sample(path_a, n=10, seed=20261014, store_root=store_a)

    assert first.doc_ids == again.doc_ids
    assert first.doc_ids == relaid.doc_ids  # secim yalniz (tohum, doc_id)'ye bagli
    assert first.doc_ids != other_seed.doc_ids
    assert len(set(first.doc_ids)) == 10 and first.population_documents == 40
    keys = [document.sample_key for document in first.documents]
    assert keys == sorted(keys)  # kor dosya sirasi anahtar sirasidir, kaynak sirasi degil
    expected = sorted(texts, key=lambda text: jury.sample_key(20261013, "doc:" + hashlib.sha256(text.encode()).hexdigest()))[:10]
    assert [document.text for document in first.documents] == expected


def test_manifest_sampling_takes_each_text_once(tmp_path: Path) -> None:
    texts = _texts(6) + [_texts(1)[0]]  # 7. belge 1. belgenin birebir kopyasi
    path, store = _manifest_source(tmp_path, texts)
    draw = jury.draw_sample(path, n=7, seed=1, store_root=store)
    assert len(draw.documents) == 6 and len(set(draw.doc_ids)) == 6
    assert draw.duplicate_occurrences == 1
    first_copy = [document for document in draw.documents if document.text == texts[0]]
    assert [document.source_ordinal for document in first_copy] == [1]


def test_manifest_sampling_refuses_shard_that_does_not_match_manifest(tmp_path: Path) -> None:
    path, store = _manifest_source(tmp_path, _texts(8))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["shards"][0]["byte_size"] += 1
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(Exception, match="size"):
        jury.draw_sample(path, n=3, seed=1, store_root=store)


def test_line_sampling_uses_line_numbers_and_skips_empty_lines(tmp_path: Path) -> None:
    lines = []
    for index in range(1, 31):
        lines.append("" if index % 5 == 0 else f"satir {index} duz metin")
    txt = tmp_path / "kaynak.txt"
    txt.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    first = jury.draw_sample(txt, n=8, seed=3)
    again = jury.draw_sample(txt, n=8, seed=3)
    assert [d.source_ordinal for d in first.documents] == [d.source_ordinal for d in again.documents]
    assert first.population_documents == 24 and first.skipped_empty == 6
    assert all(d.source_ordinal % 5 != 0 for d in first.documents)
    eligible = [index for index in range(1, 31) if index % 5 != 0]
    expected = sorted(eligible, key=lambda index: jury.sample_key(3, f"line:{index}"))[:8]
    assert [d.source_ordinal for d in first.documents] == expected
    assert all(d.text == f"satir {d.source_ordinal} duz metin" for d in first.documents)
    assert first.doc_ids == [hashlib.sha256(d.text.encode()).hexdigest() for d in first.documents]

    jsonl = tmp_path / "kaynak.jsonl"
    jsonl.write_text("".join(json.dumps({"id": f"k{i}", "text": f"jsonl metni {i}"}) + "\n" for i in range(1, 11)),
                     encoding="utf-8")
    draw = jury.draw_sample(jsonl, n=3, seed=3)
    assert all(d.text.startswith("jsonl metni ") and d.external_id == f"k{d.source_ordinal}" for d in draw.documents)


# ------------------------------------------------------------------ kor dosya


def test_blind_file_leaks_no_source_identifying_field(tmp_path: Path) -> None:
    run_dir, draw = _prepared_run(tmp_path)
    raw = (run_dir / jury.BLIND_FILE).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == 10
    for row in rows:
        assert tuple(sorted(row)) == BLIND_FIELDS
        assert "\n" not in row["metin"] and "\t" not in row["metin"] and "  " not in row["metin"]
    for document in draw.documents:
        for needle in (document.doc_id, document.url, document.dump, document.external_id, "site", "urn:uuid",
                       "quality_score", "11111111-2222", "a" * 64):
            assert needle not in raw
    # Anahtar ise eslemeyi tasir.
    key = json.loads((run_dir / jury.KEY_FILE).read_text(encoding="utf-8"))
    assert [row["doc_id"] for row in key["rows"]] == draw.doc_ids
    assert key["rows"][0]["url"].startswith("https://site")


def test_blind_text_format_does_not_reveal_line_breaks() -> None:
    with_breaks = jury.blind_row(1, "Başlık\n\nGövde  bir.\r\nGövde\tiki. ")
    flat = jury.blind_row(1, "Başlık Gövde bir. Gövde iki.")
    assert with_breaks == flat


def test_blind_row_guard_rejects_extra_fields_and_raw_whitespace() -> None:
    with pytest.raises(JuryError, match="non-blind"):
        jury.assert_blind_row_clean({"no": 1, "metin": "a", "kesildi": False, "char_count": 1, "url": "x"})
    with pytest.raises(JuryError, match="whitespace"):
        jury.assert_blind_row_clean({"no": 1, "metin": "a\nb", "kesildi": False, "char_count": 3})
    with pytest.raises(JuryError, match="whitespace"):
        jury.assert_blind_row_clean({"no": 1, "metin": "a  b", "kesildi": False, "char_count": 4})


def test_blind_text_is_cut_at_limit() -> None:
    row = jury.blind_row(1, "kelime " * 2000)
    assert row["kesildi"] is True and len(row["metin"]) == jury.BLIND_MAX_CHARS and row["char_count"] == 13999
    # Kesim bosluga denk gelirse sondaki bosluk silinir (guard bunu reddederdi).
    row = jury.blind_row(2, "abcde " * 2000)
    assert row["kesildi"] is True and row["metin"] == row["metin"].strip() and len(row["metin"]) == jury.BLIND_MAX_CHARS - 1


# ------------------------------------------------------------------ kilavuz


def test_rubric_sha_is_pinned_and_enters_judge_id() -> None:
    assert jury.rubric_sha256() == PINNED_RUBRIC_SHA256
    assert jury.judge_id("sonnet", jury.rubric_sha256()) == f"sonnet+juri-siki-v1@{PINNED_RUBRIC_SHA256[:8]}"
    assert b"\r\n" not in jury.rubric_bytes()  # LF: SHA platformdan bagimsiz
    assert jury.judge_family("claude-sonnet-5-5") == "sonnet"


def test_scoring_refuses_a_run_prepared_with_another_rubric(tmp_path: Path, monkeypatch) -> None:
    run_dir, _ = _prepared_run(tmp_path)
    changed = tmp_path / "juri-siki-v1.md"
    changed.write_bytes(jury.rubric_bytes() + b"\nbir satir daha\n")
    monkeypatch.setattr(jury, "RUBRIC_PATH", changed)
    with pytest.raises(JuryError, match="rubric"):
        jury.score_run(run_dir, pass1={}, pass2=None, judge_label="sonnet", judge_model="m")


# ------------------------------------------------------------------ karar satirlari ve sayilar


def test_external_verdicts_become_decision_rows_and_numbers(tmp_path: Path) -> None:
    run_dir, draw = _prepared_run(tmp_path)
    verdicts = ["kalsin", "cop", "emin değilim", "kalsın", "cop", "kalsin", "kalsin", "çöp", "kalsin", "kalsin"]
    p1 = _write_verdicts(tmp_path / "p1.jsonl", [
        {"no": no, "hukum": verdict, "tur": "haber", "cop_nedeni": "seo-ticari" if "c" in verdict[:1] or verdict.startswith("ç") else "", "gerekce": "x"}
        for no, verdict in enumerate(verdicts, 1)
    ])
    retest_verdicts = list(verdicts)
    retest_verdicts[2] = "cop"
    p2 = _write_verdicts(tmp_path / "p2.jsonl", [
        {"no": no, "hukum": verdict, "tur": "haber", "cop_nedeni": ""} for no, verdict in enumerate(retest_verdicts, 1)
    ])
    _run, blind, _key = jury.load_run(run_dir)
    pass1, missing1 = load_verdict_file(p1, blind)
    pass2, _ = load_verdict_file(p2, blind)
    assert missing1 == []

    numbers = jury.score_run(run_dir, pass1=pass1, pass2=pass2, judge_label="sonnet", judge_model="external:sonnet",
                             computed_at=DECIDED_AT, human={"reviewed": 200, "rejected": 18})

    rows = list(read_decisions(run_dir / jury.DECISIONS_FILE))
    assert len(rows) == 20
    first = [row for row in rows if not row["run_id"].endswith("/retest")]
    assert {row["decision_type"] for row in rows} == {"jury"}
    assert {row["judge"] for row in rows} == {f"sonnet+juri-siki-v1@{PINNED_RUBRIC_SHA256[:8]}"}
    assert [row["doc_id"] for row in first] == draw.doc_ids
    assert [row["verdict"] for row in first] == ["pass", "reject", "flag", "pass", "reject", "pass", "pass", "reject", "pass", "pass"]
    assert first[1]["reason"] == "haber/seo-ticari" and first[0]["reason"] == "haber/"
    assert numbers["decisions"]["rows"] == 20
    assert numbers["decisions"]["sha256"] == hashlib.sha256((run_dir / jury.DECISIONS_FILE).read_bytes()).hexdigest()

    junk = numbers["jury"]
    assert junk["status"] == "judged" and junk["count"] == 4 and junk["n"] == 10  # emin degilim cop tarafinda
    assert junk["strict_cop_only"]["count"] == 3
    low, high = wilson(4, 10)
    assert (junk["low"], junk["high"]) == (low, high)
    assert junk["retest"]["agreement_3class"] == 0.9 and junk["retest"]["agreement_binary"] == 1.0
    assert numbers["human"]["count"] == 18 and numbers["human"]["n"] == 200
    assert numbers["judge_id"].startswith("sonnet+juri-siki-v1@")
    assert set(numbers) >= {"pii", "rule", "jury", "human", "run_id", "decisions", "computed_at", "rubric"}
    on_disk = json.loads((run_dir / jury.NUMBERS_FILE).read_text(encoding="utf-8"))
    assert on_disk["jury"]["count"] == 4


def test_sample_numbers_count_pii_and_rule_drops(tmp_path: Path) -> None:
    texts = ["İletişim: ali@ornek.com.tr adresine yazın, kalan metin düzgün Türkçe.", "Temiz bir belge metni burada."]
    path, store = _manifest_source(tmp_path, texts)
    draw = jury.draw_sample(path, n=2, seed=1, store_root=store)
    run_dir = tmp_path / "r"
    jury.prepare_run(draw, run_dir, source_id=None, object_sha256="b" * 64, created_at=DECIDED_AT)
    numbers = jury.score_run(run_dir, pass1=None, pass2=None, judge_label=None, judge_model=None, computed_at=DECIDED_AT)
    assert numbers["pii"]["count"] == 1 and numbers["pii"]["n"] == 2
    assert numbers["pii"]["documents_by_category"] == {"email": 1}
    assert numbers["rule"]["policy"] == "tr-web-v3" and numbers["rule"]["n"] == 2


def test_verdict_file_rejects_unknown_and_duplicate_rows(tmp_path: Path) -> None:
    with pytest.raises(VerdictFileError, match="not in the blind file"):
        load_verdict_file(_write_verdicts(tmp_path / "a.jsonl", [{"no": 99, "hukum": "cop"}]), [1, 2])
    with pytest.raises(VerdictFileError, match="twice"):
        load_verdict_file(_write_verdicts(tmp_path / "b.jsonl", [{"no": 1, "hukum": "cop"}, {"no": 1, "hukum": "kalsin"}]), [1, 2])
    with pytest.raises(VerdictFileError, match="unknown verdict"):
        load_verdict_file(_write_verdicts(tmp_path / "c.jsonl", [{"no": 1, "hukum": "belki"}]), [1, 2])
    verdicts, missing = load_verdict_file(_write_verdicts(tmp_path / "d.jsonl", [{"no": 2, "hukum": "Emin Değilim"}]), [1, 2])
    assert missing == [1] and verdicts[2].verdict == "emin degilim"


# ------------------------------------------------------------------ hakem ve butce


class FakeCaller:
    def __init__(self, answer: str = '{"hukum": "cop", "tur": "urun-ticari", "cop_nedeni": "seo-ticari", "gerekce": "reklam"}',
                 stop_reason: str = "end_turn") -> None:
        self.calls: list[str] = []
        self.answer = answer
        self.stop_reason = stop_reason

    def __call__(self, message: str) -> JudgeResponse:
        self.calls.append(message)
        return JudgeResponse(text=self.answer, stop_reason=self.stop_reason, input_tokens=900, output_tokens=60,
                             cache_read_input_tokens=1200)


def _limits(**overrides: int) -> BudgetLimits:
    values = {"max_calls_per_run": 1000, "max_tokens_per_run": 10**9, "max_calls_per_day": 1000, "max_tokens_per_day": 10**9}
    values.update(overrides)
    return BudgetLimits(**values)


def test_judge_run_with_fake_caller_writes_both_passes(tmp_path: Path) -> None:
    run_dir, _ = _prepared_run(tmp_path)
    caller = FakeCaller()
    budget = JuryBudget(BudgetLedger(tmp_path / "ledger"), _limits(), "run-x")
    settings = JudgeSettings(provider="anthropic", model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY")
    pass1, pass2, cost = jury.run_judge(run_dir, caller, budget, settings=settings, retest=True)
    assert len(caller.calls) == 20 and len(pass1.verdicts) == 10 and len(pass2.verdicts) == 10
    assert "<metin>" in caller.calls[0] and "juri no 1" in caller.calls[0]
    assert cost["calls"] == 20 and cost["estimated_usd"] == round((18000 * 2 + 1200 * 10 + 24000 * 0.2) / 1e6, 4)
    assert (run_dir / jury.PASS1_FILE).exists() and (run_dir / jury.PASS2_FILE).exists()
    ledger = BudgetLedger(tmp_path / "ledger").read()
    assert ledger["calls"] == 20 and ledger["tokens"] == 20 * (900 + 60 + 1200)


def test_budget_preflight_refuses_before_any_call(tmp_path: Path) -> None:
    run_dir, _ = _prepared_run(tmp_path)
    caller = FakeCaller()
    budget = JuryBudget(BudgetLedger(tmp_path / "ledger"), _limits(max_calls_per_run=15), "run-y")
    settings = JudgeSettings(provider="anthropic", model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY")
    with pytest.raises(JuryBudgetExhausted, match="before any call"):
        jury.run_judge(run_dir, caller, budget, settings=settings, retest=True)  # 20 > 15
    assert caller.calls == []


def test_daily_counter_is_durable_and_stops_the_job(tmp_path: Path) -> None:
    run_dir, _ = _prepared_run(tmp_path)
    _run, blind, _key = jury.load_run(run_dir)
    rows = [blind[number] for number in sorted(blind)]
    ledger_dir = tmp_path / "ledger"
    clock = lambda: datetime(2026, 10, 13, 9, tzinfo=timezone.utc)  # noqa: E731
    first = FakeCaller()
    jury.judge_rows(rows[:2], first, JuryBudget(BudgetLedger(ledger_dir, clock=clock), _limits(max_calls_per_day=3), "run-1"),
                    rubric="k", max_tokens=10, label="p1")
    assert len(first.calls) == 2
    # Yeni surec / yeni kosu: sayac diskten okunur, gunluk sinirda durur.
    second = FakeCaller()
    with pytest.raises(JuryBudgetExhausted, match="daily call cap"):
        jury.judge_rows(rows, second, JuryBudget(BudgetLedger(ledger_dir, clock=clock), _limits(max_calls_per_day=3), "run-2"),
                        rubric="k", max_tokens=10, label="p1")
    assert len(second.calls) == 1
    state = json.loads((ledger_dir / "jury-budget-2026-10-13.json").read_text(encoding="utf-8"))
    assert state["calls"] == 3 and state["runs"]["run-1"]["calls"] == 2 and state["runs"]["run-2"]["calls"] == 1
    # Ertesi gun yeni defter.
    next_day = BudgetLedger(ledger_dir, clock=lambda: datetime(2026, 10, 14, 0, 1, tzinfo=timezone.utc))
    assert next_day.read()["calls"] == 0


def test_refusal_is_recorded_without_fallback(tmp_path: Path) -> None:
    run_dir, _ = _prepared_run(tmp_path, count=4, n=3)
    _run, blind, _key = jury.load_run(run_dir)
    result = jury.judge_rows([blind[1]], FakeCaller(answer="", stop_reason="refusal"),
                             JuryBudget(BudgetLedger(tmp_path / "l"), _limits(), "r"), rubric="k", max_tokens=10, label="p1")
    assert result.verdicts == {} and result.errors == {1: "refusal"}


def test_missing_key_means_judge_unavailable_and_blind_file_still_exists(tmp_path: Path, monkeypatch, capsys) -> None:
    settings, key = jury.resolve_judge(env={})
    assert key is None and settings.api_key_env == "ANTHROPIC_API_KEY" and settings.model == jury.DEFAULT_JUDGE_MODEL
    _settings, present = jury.resolve_judge(env={"ANTHROPIC_API_KEY": " sk-test ", "DERLEM_JURY_MODEL": "claude-opus-5-5"})
    assert present == "sk-test" and _settings.model == "claude-opus-5-5"

    run_dir, _ = _prepared_run(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert jury.main(["judge", "--run-dir", str(run_dir)]) == 3
    assert "judge_unavailable" in capsys.readouterr().err
    numbers = jury.score_run(run_dir, pass1=None, pass2=None, judge_label=None, judge_model=None, computed_at=DECIDED_AT)
    assert numbers["jury"]["status"] == "judge_unavailable" and numbers["judge_id"] is None
    assert (run_dir / jury.BLIND_FILE).exists() and (run_dir / jury.KEY_FILE).exists()
    assert not (run_dir / jury.DECISIONS_FILE).exists()


def test_anthropic_caller_sends_rubric_as_cached_system_prompt() -> None:
    captured = {}

    def post(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": '{"hukum":"kalsin"}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}}

    settings = JudgeSettings(provider="anthropic", model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY")
    response = jury.anthropic_judge_caller(settings, "sk-test", "KILAVUZ", post=post)("mesaj")
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-test"
    assert captured["body"]["system"] == [{"type": "text", "text": "KILAVUZ", "cache_control": {"type": "ephemeral"}}]
    assert captured["body"]["model"] == "claude-sonnet-5-5" and captured["body"]["messages"][0]["content"] == "mesaj"
    assert "sk-test" not in json.dumps(captured["body"])
    assert response.text == '{"hukum":"kalsin"}' and response.total_tokens == 115


# ------------------------------------------------------------------ istatistik ve capa


def test_wilson_and_kappa_match_the_manual_scripts() -> None:
    low, high = wilson(43, 100)
    assert round(low, 4) == 0.3373 and round(high, 4) == 0.5278  # 2026-10-04 HQ %43 [33,7-52,8]
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "a", "b", "b"]) == 1.0
    assert cohen_kappa(["a", "b"], ["b", "a"]) == -1.0
    assert cohen_kappa(["a", "a"], ["a", "a"]) is None
    report = agreement_report({1: "cop", 2: "kalsin", 3: "emin degilim"}, {1: "cop", 2: "kalsin", 3: "cop"})
    assert report["agreement_3class"] == pytest.approx(2 / 3) and report["agreement_binary"] == 1.0
    assert report["disagreements"] == [3]


def test_anchor_sheet_picks_hard_rows_and_round_trips(tmp_path: Path) -> None:
    run_dir, _ = _prepared_run(tmp_path, count=40, n=30)
    _run, blind, key = jury.load_run(run_dir)
    pass1 = {no: Verdict(no, "kalsin" if no % 3 else "cop", "haber", "" if no % 3 else "seo-ticari", "") for no in blind}
    pass1[5] = Verdict(5, "emin degilim", "blog", "", "")
    pass2 = dict(pass1)
    pass2[7] = Verdict(7, "cop", "haber", "menu-spot", "")
    chosen = choose_anchor_rows(list(key.values()), pass1, pass2, size=5)
    assert len(chosen) == 14  # alt sinir
    assert 7 in chosen and 5 in chosen
    assert len(choose_anchor_rows(list(key.values()), pass1, pass2, size=99)) == 30
    sheet = render_anchor_sheet(blind, chosen, title="t")
    for marker in ("seo-ticari", "rule", "doc_id", "kalsin\n"):
        assert marker not in sheet.split("---", 1)[1]
    filled = sheet.replace("Hukum: \n", "Hukum: cop\n", 3)
    owner = parse_anchor_sheet(filled)
    assert list(owner.values()) == ["cop", "cop", "cop"] and set(owner) <= set(chosen)


def test_mixed_blind_file_splits_back_to_runs(tmp_path: Path) -> None:
    run_a, _ = _prepared_run(tmp_path / "a", count=8, n=4)
    run_b, _ = _prepared_run(tmp_path / "b", count=8, n=4)
    mix_dir = tmp_path / "karma"
    jury.mix_runs([run_a, run_b], mix_dir, seed=5)
    rows = [json.loads(line) for line in (mix_dir / jury.BLIND_FILE).read_text(encoding="utf-8").splitlines()]
    assert [row["no"] for row in rows] == list(range(1, 9)) and all(tuple(sorted(r)) == BLIND_FIELDS for r in rows)
    verdict_file = _write_verdicts(tmp_path / "karma.jsonl", [{"no": row["no"], "hukum": "cop"} for row in rows])
    counts = jury.split_mixed_verdicts(mix_dir, verdict_file, output_name="hukumler-karma.jsonl")
    assert sorted(counts.values()) == [4, 4]
    _run, blind_a, _ = jury.load_run(run_a)
    verdicts, missing = load_verdict_file(run_a / "hukumler-karma.jsonl", blind_a)
    assert missing == [] and len(verdicts) == 4


def test_junk_numbers_report_missing_rows() -> None:
    numbers = junk_numbers({1: Verdict(1, "cop", "haber", "seo-ticari", "")}, expected=3)
    assert numbers["missing"] == 2 and numbers["n"] == 1 and numbers["junk_reasons"] == {"seo-ticari": 1}


def test_default_budget_admits_a_standard_200_row_run_with_retest() -> None:
    # 200 satir x 2 gecis, her satir kor dosyanin ust sinirinda (6000 karakter):
    # varsayilan sinirlar standart kosuyu kabul etmeli, ucuncu gecisi etmemeli.
    limits = BudgetLimits.from_env(env={})
    row = {"no": 1, "metin": "a" * jury.BLIND_MAX_CHARS, "kesildi": True, "char_count": 9000}
    per_call = jury.estimate_call_tokens(jury.rubric_text(), row, jury.DEFAULT_JUDGE_MAX_TOKENS)
    assert 400 <= limits.max_calls_per_run < 600
    assert 400 * per_call <= limits.max_tokens_per_run
    assert limits.max_calls_per_day < 3 * 400 or limits.max_tokens_per_day < 3 * 400 * per_call
