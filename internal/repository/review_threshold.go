package repository

// TASK-048: pretrain inceleme kapısında sıfır tolerans yerine eşik.
//
// Eşik kaynak satırında durur (sources.pretrain_review_reject_threshold,
// 000030). Yalnız pretrain kaynakta konur ve ilk inceleme izinden (belge
// incelemesi, kaynak incelemesi, açık inceleme talebi) sonra değişmez: çubuk
// ölçümden önce konur. Eşik yoksa (nil) kapı eski sıfır-tolerans kuralıdır,
// bayt bayt. Aynı formül DB'de source_document_review_gate_passes ve worker'da
// review_gate_passes olarak durur; üçü birlikte değişir.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
)

const (
	// ReasonReviewRejectRateAboveThreshold: pretrain örneğinde ölçülen
	// (ret + sensitive_review) / örnek oranı eşiği aşıyor.
	ReasonReviewRejectRateAboveThreshold = "review_reject_rate_above_threshold"
	// ReasonDocumentSampleReviewIncomplete: incelenmemiş örnek var ya da
	// (eşiksiz kaynakta) onaylanmamış örnek var.
	ReasonDocumentSampleReviewIncomplete = "document_sample_review_incomplete"

	reasonThresholdPurpose      = "content_purpose_not_pretrain"
	reasonThresholdInvalid      = "invalid_pretrain_review_reject_threshold"
	reasonThresholdReviewLocked = "pretrain_review_threshold_locked_review_started"
)

// pretrainThresholdBasisPoints eşiği yüzün yüzde biri (bps) olarak verir:
// 10.00 % -> 1000. Sütun numeric(5,2) olduğundan yuvarlama tamdır; kapı
// karşılaştırması tamsayıyla yapılır (flagged*10000 <= bps*sampled).
func pretrainThresholdBasisPoints(source domain.Source) (int64, bool) {
	if source.ContentPurpose != "pretrain" || source.PretrainReviewRejectThreshold == nil {
		return 0, false
	}
	return int64(math.Round(*source.PretrainReviewRejectThreshold * 100)), true
}

// documentSampleReviewReasons, örnek inceleme kapısının nedenleri (yalnız
// document_sampling_status = sampled iken çağrılır).
func documentSampleReviewReasons(source domain.Source) []string {
	sampled := source.SampledDocumentCount
	if sampled <= 0 || source.ReviewedDocumentCount != sampled {
		return []string{ReasonDocumentSampleReviewIncomplete}
	}
	thresholdBPS, thresholdMode := pretrainThresholdBasisPoints(source)
	if !thresholdMode {
		if source.ApprovedDocumentCount != sampled || source.FlaggedDocumentCount > 0 {
			return []string{ReasonDocumentSampleReviewIncomplete}
		}
		return nil
	}
	if source.ApprovedDocumentCount+source.FlaggedDocumentCount != sampled {
		return []string{ReasonDocumentSampleReviewIncomplete}
	}
	if source.FlaggedDocumentCount*10000 > thresholdBPS*sampled {
		return []string{ReasonReviewRejectRateAboveThreshold}
	}
	return nil
}

func formatBasisPoints(value int64) string {
	return fmt.Sprintf("%d.%02d", value/100, value%100)
}

// reviewRejectRateDetail, eşik aşıldığında ölçülen oranı ve eşiği metne döker.
func reviewRejectRateDetail(source domain.Source, reasons []string) string {
	thresholdBPS, thresholdMode := pretrainThresholdBasisPoints(source)
	if !thresholdMode || source.SampledDocumentCount <= 0 {
		return ""
	}
	for _, reason := range reasons {
		if reason != ReasonReviewRejectRateAboveThreshold {
			continue
		}
		sampled := source.SampledDocumentCount
		rateBPS := (source.FlaggedDocumentCount*10000 + sampled/2) / sampled
		return fmt.Sprintf(
			"measured reject rate %s%% (%d rejected or flagged of %d sampled) > threshold %s%%",
			formatBasisPoints(rateBPS), source.FlaggedDocumentCount, sampled,
			formatBasisPoints(thresholdBPS),
		)
	}
	return ""
}

// validPretrainReviewThreshold: 0-100, en çok iki ondalık; nil (eşiği kaldır)
// geçerlidir.
func validPretrainReviewThreshold(value *float64) bool {
	if value == nil {
		return true
	}
	v := *value
	if math.IsNaN(v) || math.IsInf(v, 0) || v < 0 || v > 100 {
		return false
	}
	return math.Abs(v*100-math.Round(v*100)) < 1e-6
}

// pretrainThresholdChangeReasons, eşik yazımının kapı nedenleri.
// reviewStarted: kaynakta herhangi bir inceleme izi var (sayaç, belge
// incelemesi, kaynak incelemesi ya da inceleme talebi).
func pretrainThresholdChangeReasons(contentPurpose string, reviewStarted bool, value *float64) []string {
	reasons := []string{}
	if contentPurpose != "pretrain" {
		reasons = append(reasons, reasonThresholdPurpose)
	}
	if !validPretrainReviewThreshold(value) {
		reasons = append(reasons, reasonThresholdInvalid)
	}
	if reviewStarted {
		reasons = append(reasons, reasonThresholdReviewLocked)
	}
	return reasons
}

func sameThreshold(left, right *float64) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return math.Round(*left*100) == math.Round(*right*100)
}

// SetPretrainReviewThreshold, pretrain kaynağın inceleme eşiğini yazar (nil =
// eşiği kaldır, sıfır toleransa dön). İnceleme başladıktan sonra reddedilir;
// aynı kural DB tetikleyicisinde de vardır (lock_pretrain_review_threshold).
func (r *Sources) SetPretrainReviewThreshold(
	ctx context.Context,
	sourceID string,
	value *float64,
	actorID string,
) (domain.Source, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, err
	}
	defer tx.Rollback(ctx)

	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1 FOR UPDATE", sourceID,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, ErrNotFound
	}
	if err != nil {
		return domain.Source{}, err
	}

	var reviewStarted bool
	if err := tx.QueryRow(ctx, `
		SELECT $2::bigint > 0
			OR EXISTS (
				SELECT 1
				FROM document_reviews AS review
				JOIN documents AS document ON document.id = review.document_id
				WHERE document.source_id = $1
			)
			OR EXISTS (SELECT 1 FROM reviews AS review WHERE review.source_id = $1)
			OR EXISTS (
				SELECT 1
				FROM document_review_claims AS claim
				JOIN documents AS document ON document.id = claim.document_id
				WHERE document.source_id = $1
			)
	`, sourceID, source.ReviewedDocumentCount).Scan(&reviewStarted); err != nil {
		return domain.Source{}, err
	}

	if reasons := pretrainThresholdChangeReasons(source.ContentPurpose, reviewStarted, value); len(reasons) > 0 {
		return domain.Source{}, &GateError{Reasons: reasons}
	}
	if sameThreshold(source.PretrainReviewRejectThreshold, value) {
		return source, tx.Commit(ctx)
	}

	updated, err := scanSource(tx.QueryRow(ctx, `
		UPDATE sources
		SET pretrain_review_reject_threshold = $1::numeric(5, 2)
		WHERE id = $2
		RETURNING `+sourceColumns,
		value, sourceID,
	))
	if err != nil {
		return domain.Source{}, fmt.Errorf("update pretrain review threshold: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"threshold_before": source.PretrainReviewRejectThreshold,
		"threshold_after":  updated.PretrainReviewRejectThreshold,
		"source_version":   updated.Version,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.pretrain_review_threshold_set', 'source', $2, $3::jsonb)
	`, actorID, sourceID, details); err != nil {
		return domain.Source{}, fmt.Errorf("audit pretrain review threshold: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, err
	}
	return updated, nil
}
