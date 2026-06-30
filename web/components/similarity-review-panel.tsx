"use client";

import {
  AlertTriangle,
  Check,
  ChevronRight,
  CircleHelp,
  CopyCheck,
  Equal,
  GitCompareArrows,
  LoaderCircle,
  RefreshCw,
  Unlink,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { messageFrom, requestJSON } from "@/lib/client-api";
import type {
  SimilarityCalibrationRun,
  SimilarityPairDetail,
  SimilarityReviewLabel,
  SimilarityReviewPair,
  User,
} from "@/lib/types";

const labelDetails: Record<SimilarityReviewLabel, { label: string; icon: typeof Equal }> = {
  exact_duplicate: { label: "Aynı", icon: Equal },
  near_duplicate: { label: "Yakın tekrar", icon: CopyCheck },
  related: { label: "İlişkili", icon: GitCompareArrows },
  different: { label: "Farklı", icon: Unlink },
  uncertain: { label: "Kararsız", icon: CircleHelp },
};

type Props = {
  user: User;
  onNotice: (message: string | null) => void;
};

export function SimilarityReviewPanel({ user, onNotice }: Props) {
  const [runs, setRuns] = useState<SimilarityCalibrationRun[]>([]);
  const [selectedRunID, setSelectedRunID] = useState("");
  const [pairs, setPairs] = useState<SimilarityReviewPair[]>([]);
  const [selectedPairID, setSelectedPairID] = useState("");
  const [detail, setDetail] = useState<SimilarityPairDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [label, setLabel] = useState<SimilarityReviewLabel>("near_duplicate");

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunID) ?? null,
    [runs, selectedRunID],
  );
  const canReview = user.roles.some((role) => ["admin", "moderator", "expert_reviewer"].includes(role));

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await requestJSON<{ items: SimilarityCalibrationRun[] }>("/api/similarity-calibrations");
      setRuns(payload.items);
      setSelectedRunID((current) => current || payload.items[0]?.id || "");
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice]);

  const loadPairs = useCallback(async (runID: string) => {
    if (!runID) {
      setPairs([]);
      return;
    }
    setLoading(true);
    try {
      const payload = await requestJSON<{ items: SimilarityReviewPair[] }>(
        `/api/similarity-calibrations/${encodeURIComponent(runID)}/pairs?limit=200`,
      );
      setPairs(payload.items);
      setSelectedPairID((current) =>
        payload.items.some((pair) => pair.id === current) ? current : payload.items[0]?.id || "",
      );
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice]);

  const loadDetail = useCallback(async (pairID: string) => {
    if (!pairID) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    try {
      const payload = await requestJSON<SimilarityPairDetail>(
        `/api/similarity-pairs/${encodeURIComponent(pairID)}`,
      );
      setDetail(payload);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoadingDetail(false);
    }
  }, [onNotice]);

  useEffect(() => { void loadRuns(); }, [loadRuns]);
  useEffect(() => { void loadPairs(selectedRunID); }, [loadPairs, selectedRunID]);
  useEffect(() => { void loadDetail(selectedPairID); }, [loadDetail, selectedPairID]);

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || detail.pair.current_reviewer_label) return;
    const form = event.currentTarget;
    const reason = String(new FormData(form).get("reason") ?? "").trim();
    setSubmitting(true);
    try {
      await requestJSON(`/api/similarity-pairs/${encodeURIComponent(detail.pair.id)}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, reason: reason || null }),
      });
      form.reset();
      onNotice("Benzerlik kararı kaydedildi.");
      await Promise.all([loadRuns(), loadPairs(selectedRunID), loadDetail(detail.pair.id)]);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSubmitting(false);
    }
  }

  if (!loading && runs.length === 0) {
    return (
      <section className="similarity-empty">
        <GitCompareArrows size={26} aria-hidden="true" />
        <p>İçe aktarılmış kalibrasyon incelemesi yok.</p>
      </section>
    );
  }

  return (
    <section className="similarity-workspace">
      <div className="similarity-run-bar">
        <label>
          <span>Kalibrasyon</span>
          <select value={selectedRunID} onChange={(event) => { setSelectedRunID(event.target.value); setSelectedPairID(""); }}>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.content_purpose} · {run.source_snapshot[0]?.name ?? run.report_object_sha256.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <button className="icon-button" type="button" title="Benzerlik verilerini yenile" onClick={() => void loadRuns()}>
          <RefreshCw className={loading ? "spin" : ""} size={18} aria-hidden="true" />
        </button>
      </div>

      {selectedRun && (
        <div className="similarity-metrics">
          <SimilarityMetric label="Çift" value={selectedRun.pair_count} />
          <SimilarityMetric label="İncelenen" value={selectedRun.reviewed_pair_count} />
          <SimilarityMetric label="Bağımsız karar" value={selectedRun.independent_review_count} />
          <SimilarityMetric label="Uzlaşı" value={selectedRun.consensus_pair_count} tone="good" />
          <SimilarityMetric label="Uyuşmazlık" value={selectedRun.disagreement_pair_count} tone="warn" />
        </div>
      )}

      <div className="similarity-layout">
        <div className="similarity-pair-list" aria-label="Benzerlik çiftleri">
          {pairs.map((pair) => (
            <button
              key={pair.id}
              data-testid={`similarity-pair-${pair.pair_rank}`}
              type="button"
              className={pair.id === selectedPairID ? "active" : undefined}
              onClick={() => setSelectedPairID(pair.id)}
            >
              <span className="similarity-rank">#{pair.pair_rank}</span>
              <span>
                <strong>Hamming {pair.hamming_distance}</strong>
                <small>{pair.left_token_count.toLocaleString("tr-TR")} / {pair.right_token_count.toLocaleString("tr-TR")} token</small>
              </span>
              <PairState pair={pair} />
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          ))}
        </div>

        <div className="similarity-detail">
          {loadingDetail ? (
            <div className="similarity-loading"><LoaderCircle className="spin" size={22} /><span>Çift açılıyor</span></div>
          ) : detail ? (
            <>
              <header className="similarity-detail-header">
                <div>
                  <span>Çift #{detail.pair.pair_rank}</span>
                  <h2>Hamming {detail.pair.hamming_distance}</h2>
                </div>
                {detail.pair.has_disagreement ? (
                  <span className="similarity-state disagreement"><AlertTriangle size={15} />Uyuşmazlık</span>
                ) : detail.pair.consensus_label ? (
                  <span className="similarity-state consensus"><Check size={15} />{labelDetails[detail.pair.consensus_label].label}</span>
                ) : null}
              </header>

              <div className="similarity-documents">
                <SimilarityDocument
                  side="A"
                  ordinal={detail.pair.left_source_ordinal}
                  tokenCount={detail.pair.left_token_count}
                  content={detail.left_content}
                />
                <SimilarityDocument
                  side="B"
                  ordinal={detail.pair.right_source_ordinal}
                  tokenCount={detail.pair.right_token_count}
                  content={detail.right_content}
                />
              </div>

              {canReview && !detail.pair.current_reviewer_label && (
                <form className="similarity-review-form" onSubmit={submitReview}>
                  <fieldset>
                    <legend>Karar</legend>
                    <div className="similarity-label-options">
                      {(Object.entries(labelDetails) as [SimilarityReviewLabel, (typeof labelDetails)[SimilarityReviewLabel]][]).map(([value, item]) => {
                        const Icon = item.icon;
                        return (
                          <label key={value} className={label === value ? "selected" : undefined}>
                            <input type="radio" name="label" value={value} checked={label === value} onChange={() => setLabel(value)} />
                            <Icon size={16} aria-hidden="true" />
                            <span>{item.label}</span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                  <label className="similarity-reason">Gerekçe<textarea name="reason" maxLength={2000} required={label === "uncertain"} /></label>
                  <button className="primary-button" type="submit" disabled={submitting}>
                    {submitting ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}Kararı kaydet
                  </button>
                </form>
              )}

              {detail.pair.current_reviewer_label && (
                <div className="similarity-own-review">
                  <Check size={16} aria-hidden="true" />
                  Kararınız: {labelDetails[detail.pair.current_reviewer_label].label}
                </div>
              )}

              {detail.reviews.length > 0 && (
                <div className="similarity-review-history">
                  {detail.reviews.map((review) => (
                    <div key={review.id}>
                      <span className={`similarity-label ${review.label}`}>{labelDetails[review.label].label}</span>
                      <strong>{review.reviewer}</strong>
                      <small>{new Date(review.created_at).toLocaleString("tr-TR")}</small>
                      {review.reason && <p>{review.reason}</p>}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function SimilarityMetric({ label, value, tone }: { label: string; value: number; tone?: "good" | "warn" }) {
  return <div className={tone ? `similarity-metric ${tone}` : "similarity-metric"}><span>{label}</span><strong>{value.toLocaleString("tr-TR")}</strong></div>;
}

function PairState({ pair }: { pair: SimilarityReviewPair }) {
  if (pair.has_disagreement) return <span className="pair-state disagreement"><AlertTriangle size={14} />{pair.review_count}</span>;
  if (pair.consensus_label) return <span className="pair-state consensus"><Check size={14} />{pair.review_count}</span>;
  if (pair.current_reviewer_label) return <span className="pair-state reviewed"><Check size={14} />{pair.review_count}</span>;
  return <span className="pair-state">{pair.review_count}</span>;
}

function SimilarityDocument({ side, ordinal, tokenCount, content }: { side: string; ordinal: number; tokenCount: number; content: string }) {
  return (
    <article>
      <header><strong>Belge {side}</strong><span>#{ordinal.toLocaleString("tr-TR")} · {tokenCount.toLocaleString("tr-TR")} token</span></header>
      <pre>{content}</pre>
    </article>
  );
}
