"""TASK-048: pretrain inceleme kapisinda esik, atilacak liste ve olculen oran.

Esik kaynak satirinda durur (``sources.pretrain_review_reject_threshold``, yuzde,
0-100, iki ondalik; migration 000030). NULL = esik yok = eski sifir tolerans.
Ayni kapi formulu uc yerde durur ve birlikte degisir: DB
``source_document_review_gate_passes``, Go ``documentSampleReviewReasons``,
burada ``review_gate_passes``.

Dondurma (freeze) esikli pretrain kaynaginda:

1. Ornekte reddedilen (``rejected``) ve isaretlenen (``sensitive_review``) her
   belge icin ``derlem.decision.v1`` satiri yazar: ``decision_type=human_review``,
   verdict ``reject``/``flag``, ``judge`` = inceleyen kullanici kimligi,
   ``run_id`` = release kimligi. Dosya icerik adresli depoya girer, SHA'si
   manifeste yazilir.
2. Hariç tutma tam metin eslemesiyle yapilir: ``doc_id = sha256(metin)``, metin
   ihracatin kullandigi belge metnidir (``_document_from_line``). Ayni metin
   kaynakta birden cok kez geciyorsa HEPSI duser; fazlalik manifestte sayilir
   (``extra_occurrence_count``).
3. Manifeste olculen oran, esik, inceleyenler ve atilan kimlik listesinin
   SHA'si girer; model karti satiri da manifestte hazir durur.

Ihracat (txt/jsonl) dondurulmus manifestteki karar dosyasini okur, kimlik
listesinin SHA'sini manifestle karsilastirir ve bu belgeleri yazmaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from typing import Iterable, Mapping

from derlem_worker.releases import ReleaseGateError
from derlem_worker.sampling import _bounded_lines, _document_from_line


HUMAN_REVIEW_SCHEMA_VERSION = "derlem.human-review.v1"
HUMAN_REVIEW_METHOD = "sample-review-threshold-v1"
EXCLUSION_METHOD = "document-text-sha256-exact-v1"
DOC_ID_LIST_METHOD = "sorted-unique-doc-id-lf-sha256-v1"
# document_reviews.decision -> derlem.decision.v1 verdict
DROP_VERDICTS: Mapping[str, str] = {"rejected": "reject", "sensitive_review": "flag"}


def threshold_basis_points(threshold: object) -> int | None:
    """Yuzde esigi yuzun yuzde birine (bps) cevirir: 10 -> 1000. None -> None.

    Esik numeric(5,2)'dir; iki ondaligi asan ya da 0-100 disi deger hatadir.
    """
    if threshold is None:
        return None
    try:
        value = Decimal(str(threshold))
    except InvalidOperation as error:
        raise ValueError(f"invalid review threshold: {threshold!r}") from error
    scaled = value * 100
    if scaled != scaled.to_integral_value() or not (0 <= scaled <= 10_000):
        raise ValueError(f"review threshold must be 0-100 with at most two decimals: {threshold!r}")
    return int(scaled)


def threshold_active(content_purpose: object, threshold: object) -> bool:
    return content_purpose == "pretrain" and threshold is not None


def review_gate_passes(
    content_purpose: object,
    threshold: object,
    sampled: int,
    reviewed: int,
    approved: int,
    flagged: int,
) -> bool:
    """Ornek inceleme kapisi; ``flagged`` = reddedilen + sensitive_review."""
    sampled, reviewed, approved, flagged = int(sampled), int(reviewed), int(approved), int(flagged)
    if sampled <= 0 or reviewed != sampled:
        return False
    if approved == sampled and flagged == 0:
        return True
    if not threshold_active(content_purpose, threshold):
        return False
    threshold_bps = threshold_basis_points(threshold)
    assert threshold_bps is not None
    return approved + flagged == sampled and flagged * 10_000 <= threshold_bps * sampled


def format_basis_points(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def rate_basis_points(dropped: int, sampled: int) -> int:
    if sampled <= 0:
        return 0
    return (dropped * 10_000 + sampled // 2) // sampled


def doc_id_list_sha256(doc_ids: Iterable[str]) -> str:
    unique = sorted(set(doc_ids))
    return hashlib.sha256("".join(f"{doc_id}\n" for doc_id in unique).encode("ascii")).hexdigest()


def line_document_id(stripped_line: str) -> str | None:
    """Ihracatin belge kimligi: belge metninin SHA256'si (bos metin -> None)."""
    text, _ = _document_from_line(stripped_line)
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DroppedDocument:
    doc_id: str
    document_id: str
    source_ordinal: int
    decision: str
    reviewer_id: str

    @property
    def verdict(self) -> str:
        return DROP_VERDICTS[self.decision]


@dataclass(frozen=True)
class HumanReviewDropList:
    source_id: str
    sampled: int
    approved: int
    rejected: int
    flagged: int
    threshold_bps: int
    reviewer_ids: tuple[str, ...]
    dropped: tuple[DroppedDocument, ...]
    occurrence_counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def excluded_doc_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.doc_id for item in self.dropped}))

    @property
    def excluded_line_count(self) -> int:
        return sum(self.occurrence_counts.get(doc_id, 0) for doc_id in self.excluded_doc_ids)

    @property
    def rate_bps(self) -> int:
        return rate_basis_points(self.rejected + self.flagged, self.sampled)

    def decision_rows(self, *, run_id: str, decided_at: datetime) -> list[dict[str, object]]:
        from derlem_worker.document_record import make_decision

        rows = [
            make_decision(
                doc_id=item.doc_id,
                decision_type="human_review",
                verdict=item.verdict,
                judge=item.reviewer_id,
                run_id=run_id,
                decided_at=decided_at,
                reason=f"document_review={item.decision};sample_ordinal={item.source_ordinal}",
                # Hukum metne aittir (ayni metnin her gecisi duser): belge duzeyi.
                source_ordinal=None,
            )
            for item in self.dropped
        ]
        rows.sort(key=lambda row: (str(row["doc_id"]), str(row["reason"])))
        return rows

    def model_card_line(self) -> str:
        return human_review_model_card_line(
            sampled=self.sampled,
            rejected=self.rejected,
            flagged=self.flagged,
            threshold_bps=self.threshold_bps,
            excluded_doc_id_count=len(self.excluded_doc_ids),
            excluded_line_count=self.excluded_line_count,
            reviewer_count=len(self.reviewer_ids),
        )

    def manifest_block(self, decisions: Mapping[str, object]) -> dict[str, object]:
        excluded = self.excluded_doc_ids
        return {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "method": HUMAN_REVIEW_METHOD,
            "exclusion_method": EXCLUSION_METHOD,
            "sampled": self.sampled,
            "approved": self.approved,
            "rejected": self.rejected,
            "flagged": self.flagged,
            "rate_bps": self.rate_bps,
            "rate_pct": format_basis_points(self.rate_bps),
            "threshold_bps": self.threshold_bps,
            "threshold_pct": format_basis_points(self.threshold_bps),
            "reviewer_ids": list(self.reviewer_ids),
            "excluded_doc_id_count": len(excluded),
            "excluded_line_count": self.excluded_line_count,
            # Ayni metnin kaynakta tekrar gecisleri de duser; fazlalik burada sayilir.
            "extra_occurrence_count": self.excluded_line_count - len(excluded),
            "excluded_doc_ids_method": DOC_ID_LIST_METHOD,
            "excluded_doc_ids_sha256": doc_id_list_sha256(excluded),
            "decisions": dict(decisions),
            "model_card_line": self.model_card_line(),
        }


def human_review_model_card_line(
    *,
    sampled: int,
    rejected: int,
    flagged: int,
    threshold_bps: int,
    excluded_doc_id_count: int,
    excluded_line_count: int,
    reviewer_count: int,
) -> str:
    rate = format_basis_points(rate_basis_points(rejected + flagged, sampled))
    return (
        f"Human sample review: {rejected} rejected + {flagged} flagged of {sampled} sampled "
        f"documents = {rate}% (threshold {format_basis_points(threshold_bps)}%, set before review; "
        f"{reviewer_count} reviewer(s)); {excluded_doc_id_count} reviewed texts dropped from the "
        f"release ({excluded_line_count} lines, every occurrence)."
    )


def _blocked(reason: str, source_id: str, **details: object) -> ReleaseGateError:
    return ReleaseGateError(
        f"Human review drop list blocked: {reason}",
        {"document_review_gate": {"status": "blocked", "reason": reason, "source_id": source_id, **details}},
    )


def build_human_review_drop_list(
    *,
    source_id: str,
    source_path: Path,
    review_rows: Iterable[Mapping[str, object]],
    content_purpose: object,
    threshold: object,
    sampled_document_count: int,
    flagged_document_count: int,
    max_document_bytes: int,
) -> HumanReviewDropList:
    """Ornek inceleme satirlarindan atilacak listeyi kurar ve kaynakta dogrular.

    ``review_rows``: o kaynagin aktif ornek belgeleri (``document_id``,
    ``source_ordinal``, ``decision``, ``reviewer_id``). Her ornek incelenmis
    olmali; ret+isaret sayisi kaynak sayaciyla ve esikle tutmali; reddedilen her
    belgenin metni kaynakta o sira numarasinda bulunmali. Biri tutmazsa dondurma
    durur.
    """
    if not threshold_active(content_purpose, threshold):
        raise _blocked("review_threshold_not_active", source_id)
    threshold_bps = threshold_basis_points(threshold)
    assert threshold_bps is not None
    rows = sorted(
        (dict(row) for row in review_rows),
        key=lambda row: (int(row.get("source_ordinal") or 0), str(row.get("document_id") or "")),
    )
    sampled = int(sampled_document_count)
    if sampled <= 0 or len(rows) != sampled:
        raise _blocked("review_rows_do_not_cover_sample", source_id, sampled=sampled, rows=len(rows))
    approved = 0
    targets: list[dict[str, object]] = []
    reviewers: set[str] = set()
    for row in rows:
        decision = row.get("decision")
        reviewer_id = str(row.get("reviewer_id") or "")
        if not reviewer_id or not row.get("document_id") or int(row.get("source_ordinal") or 0) <= 0:
            raise _blocked("review_row_incomplete", source_id, document_id=str(row.get("document_id") or ""))
        reviewers.add(reviewer_id)
        if decision == "approved":
            approved += 1
        elif decision in DROP_VERDICTS:
            targets.append(row)
        else:
            raise _blocked("review_row_unreviewed", source_id, document_id=str(row.get("document_id")))
    rejected = sum(1 for row in targets if row["decision"] == "rejected")
    flagged = len(targets) - rejected
    if rejected + flagged != int(flagged_document_count):
        raise _blocked(
            "review_counts_do_not_match_source",
            source_id,
            rows_rejected_or_flagged=rejected + flagged,
            source_flagged_document_count=int(flagged_document_count),
        )
    if not review_gate_passes(content_purpose, threshold, sampled, sampled, approved, rejected + flagged):
        raise _blocked(
            "review_reject_rate_above_threshold",
            source_id,
            rate_pct=format_basis_points(rate_basis_points(rejected + flagged, sampled)),
            threshold_pct=format_basis_points(threshold_bps),
        )

    # 1. gecis: hedef sira numaralarindaki metnin kimligi (son hedefte durur).
    wanted = {int(row["source_ordinal"]): row for row in targets}
    found: dict[int, str] = {}
    if wanted:
        last = max(wanted)
        for ordinal, raw_line, oversized in _bounded_lines(source_path, max_document_bytes):
            if ordinal > last:
                break
            if ordinal not in wanted:
                continue
            if oversized or raw_line is None:
                raise _blocked("reviewed_document_oversized", source_id, source_ordinal=ordinal)
            doc_id = line_document_id(raw_line.strip())
            if doc_id is None:
                raise _blocked("reviewed_document_empty", source_id, source_ordinal=ordinal)
            found[ordinal] = doc_id
    missing = sorted(set(wanted) - set(found))
    if missing:
        raise _blocked("reviewed_document_not_in_source", source_id, source_ordinal=missing[0])

    dropped = tuple(
        DroppedDocument(
            doc_id=found[ordinal],
            document_id=str(wanted[ordinal]["document_id"]),
            source_ordinal=ordinal,
            decision=str(wanted[ordinal]["decision"]),
            reviewer_id=str(wanted[ordinal]["reviewer_id"]),
        )
        for ordinal in sorted(wanted)
    )

    # 2. gecis: atilan her metnin kaynaktaki butun gecisleri.
    excluded = {item.doc_id for item in dropped}
    occurrences = {doc_id: 0 for doc_id in excluded}
    if excluded:
        for ordinal, raw_line, oversized in _bounded_lines(source_path, max_document_bytes):
            if oversized or raw_line is None:
                continue
            stripped = raw_line.strip()
            if not stripped:
                continue
            doc_id = line_document_id(stripped)
            if doc_id in occurrences:
                occurrences[doc_id] += 1

    return HumanReviewDropList(
        source_id=source_id,
        sampled=sampled,
        approved=approved,
        rejected=rejected,
        flagged=flagged,
        threshold_bps=threshold_bps,
        reviewer_ids=tuple(sorted(reviewers)),
        dropped=dropped,
        occurrence_counts=occurrences,
    )


def write_human_review_decisions(
    drop_list: HumanReviewDropList,
    path: Path,
    *,
    run_id: str,
    decided_at: datetime,
):
    """Atilacak listeyi ``derlem.decision.v1`` Parquet dosyasi olarak yazar."""
    from derlem_worker.document_record import DECISION_SCHEMA, ParquetRowWriter, validate_decision

    writer = ParquetRowWriter(path, DECISION_SCHEMA, validator=validate_decision)
    try:
        for row in drop_list.decision_rows(run_id=run_id, decided_at=decided_at):
            writer.add(row)
    except BaseException:
        writer.abort()
        raise
    return writer.close()


def summarize_release_human_review(blocks: Mapping[str, Mapping[str, object]]) -> dict[str, object] | None:
    """Release duzeyi ozet; esik release sabitidir (kaynaklar arasinda ayni olmali)."""
    if not blocks:
        return None
    thresholds = {int(block["threshold_bps"]) for block in blocks.values()}
    if len(thresholds) != 1:
        raise ReleaseGateError(
            "Pretrain review thresholds differ between release sources",
            {
                "document_review_gate": {
                    "status": "blocked",
                    "reason": "review_threshold_not_release_constant",
                    "threshold_pct": sorted(format_basis_points(value) for value in thresholds),
                }
            },
        )
    threshold_bps = thresholds.pop()
    sampled = sum(int(block["sampled"]) for block in blocks.values())
    rejected = sum(int(block["rejected"]) for block in blocks.values())
    flagged = sum(int(block["flagged"]) for block in blocks.values())
    excluded_doc_id_count = sum(int(block["excluded_doc_id_count"]) for block in blocks.values())
    excluded_line_count = sum(int(block["excluded_line_count"]) for block in blocks.values())
    reviewer_ids = sorted({str(reviewer) for block in blocks.values() for reviewer in block["reviewer_ids"]})  # type: ignore[union-attr]
    rate_bps = rate_basis_points(rejected + flagged, sampled)
    return {
        "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
        "method": HUMAN_REVIEW_METHOD,
        "source_ids": sorted(blocks),
        "sampled": sampled,
        "rejected": rejected,
        "flagged": flagged,
        "rate_bps": rate_bps,
        "rate_pct": format_basis_points(rate_bps),
        "threshold_bps": threshold_bps,
        "threshold_pct": format_basis_points(threshold_bps),
        "reviewer_ids": reviewer_ids,
        "excluded_doc_id_count": excluded_doc_id_count,
        "excluded_line_count": excluded_line_count,
        "excluded_doc_ids_method": DOC_ID_LIST_METHOD,
        "excluded_doc_ids_sha256": hashlib.sha256(
            "".join(
                f"{source_id}:{block['excluded_doc_ids_sha256']}\n"
                for source_id, block in sorted(blocks.items())
            ).encode("ascii")
        ).hexdigest(),
        "model_card_line": human_review_model_card_line(
            sampled=sampled,
            rejected=rejected,
            flagged=flagged,
            threshold_bps=threshold_bps,
            excluded_doc_id_count=excluded_doc_id_count,
            excluded_line_count=excluded_line_count,
            reviewer_count=len(reviewer_ids),
        ),
    }


def load_excluded_doc_ids(decisions_path: Path, block: Mapping[str, object]) -> frozenset[str]:
    """Dondurulmus karar dosyasindan atilacak kimlikleri okur ve manifestle baglar."""
    from derlem_worker.document_record import read_decisions

    doc_ids: set[str] = set()
    for row in read_decisions(decisions_path):
        if row["decision_type"] != "human_review" or row["verdict"] not in {"reject", "flag"}:
            raise ValueError("human review decision file contains a non-drop decision")
        doc_ids.add(str(row["doc_id"]))
    if doc_id_list_sha256(doc_ids) != block.get("excluded_doc_ids_sha256") or len(doc_ids) != int(
        block.get("excluded_doc_id_count") or 0
    ):
        raise ValueError("human review decision file does not match the release manifest")
    return frozenset(doc_ids)
