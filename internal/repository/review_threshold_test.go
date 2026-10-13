package repository

import (
	"reflect"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

// TASK-048. Eşik 10 kurucunun ÖNERİSİdir; kodda varsayılan yoktur, değer yalnız
// testte ve dokümanda geçer.
const proposedThresholdPercent = 10.0

func thresholdTestSource(purpose string, threshold *float64, sampled, approved, flagged int64) domain.Source {
	digest := "0123456789012345678901234567890123456789012345678901234567890123"
	evidence := "license/evidence"
	return domain.Source{
		ObjectSHA256: &digest, RightsStatus: "cleared", LicenseEvidenceRef: &evidence,
		PIIStatus: "clear", DuplicateStatus: "unique", NormalizedDedupStatus: "unique",
		DocumentSamplingStatus: "sampled", ContentPurpose: purpose,
		SampledDocumentCount: sampled, ReviewedDocumentCount: approved + flagged,
		ApprovedDocumentCount: approved, FlaggedDocumentCount: flagged,
		ApprovalStatus:                "sampled_for_review",
		PretrainReviewRejectThreshold: threshold,
	}
}

func floatPointer(value float64) *float64 { return &value }

func TestPretrainReviewThresholdGate(t *testing.T) {
	ten := floatPointer(proposedThresholdPercent)
	tests := []struct {
		name   string
		source domain.Source
		want   []string
	}{
		{"threshold 10: 20/200 passes", thresholdTestSource("pretrain", ten, 200, 180, 20), []string{}},
		{"threshold 10: 21/200 fails", thresholdTestSource("pretrain", ten, 200, 179, 21),
			[]string{ReasonReviewRejectRateAboveThreshold}},
		{"threshold 10: 0/200 passes", thresholdTestSource("pretrain", ten, 200, 200, 0), []string{}},
		{"threshold 10: unreviewed sample stays incomplete", func() domain.Source {
			source := thresholdTestSource("pretrain", ten, 200, 180, 19)
			return source // reviewed 199 of 200
		}(), []string{ReasonDocumentSampleReviewIncomplete}},
		{"threshold 10: reviewed counter below sample stays incomplete", func() domain.Source {
			source := thresholdTestSource("pretrain", ten, 200, 180, 20)
			source.ReviewedDocumentCount = 199
			return source
		}(), []string{ReasonDocumentSampleReviewIncomplete}},
		{"threshold 0: one rejection fails", thresholdTestSource("pretrain", floatPointer(0), 200, 199, 1),
			[]string{ReasonReviewRejectRateAboveThreshold}},
		{"threshold 0: clean sample passes", thresholdTestSource("pretrain", floatPointer(0), 200, 200, 0), []string{}},
		{"threshold 10.5: 21/200 passes", thresholdTestSource("pretrain", floatPointer(10.5), 200, 179, 21), []string{}},
		{"threshold 10.49: 21/200 fails", thresholdTestSource("pretrain", floatPointer(10.49), 200, 179, 21),
			[]string{ReasonReviewRejectRateAboveThreshold}},
		{"threshold 100: all rejected passes", thresholdTestSource("pretrain", floatPointer(100), 200, 0, 200), []string{}},
		{"threshold NULL: pretrain keeps zero tolerance", thresholdTestSource("pretrain", nil, 200, 180, 20),
			[]string{ReasonDocumentSampleReviewIncomplete}},
		{"threshold NULL: clean pretrain passes", thresholdTestSource("pretrain", nil, 200, 200, 0), []string{}},
		{"instruction ignores threshold", thresholdTestSource("instruction", ten, 200, 199, 1),
			[]string{ReasonDocumentSampleReviewIncomplete}},
		{"contribution ignores threshold", thresholdTestSource("contribution", ten, 200, 199, 1),
			[]string{ReasonDocumentSampleReviewIncomplete}},
		{"eval ignores threshold", thresholdTestSource("eval", ten, 200, 199, 1),
			[]string{ReasonDocumentSampleReviewIncomplete}},
		{"holdout ignores threshold", thresholdTestSource("holdout", ten, 200, 199, 1),
			[]string{ReasonDocumentSampleReviewIncomplete}},
		{"empty sample stays incomplete under threshold", thresholdTestSource("pretrain", ten, 0, 0, 0),
			[]string{ReasonDocumentSampleReviewIncomplete}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := approvalGateReasons(test.source); !reflect.DeepEqual(got, test.want) {
				t.Fatalf("approvalGateReasons() = %#v, want %#v", got, test.want)
			}
		})
	}
}

func TestPretrainReviewThresholdDetailCarriesRateAndThreshold(t *testing.T) {
	source := thresholdTestSource("pretrain", floatPointer(proposedThresholdPercent), 200, 179, 21)
	reasons := approvalGateReasons(source)
	detail := reviewRejectRateDetail(source, reasons)
	for _, want := range []string{"10.50%", "21 rejected or flagged of 200 sampled", "threshold 10.00%"} {
		if !strings.Contains(detail, want) {
			t.Fatalf("detail %q does not contain %q", detail, want)
		}
	}
	gate := &GateError{Reasons: reasons, Detail: detail}
	if !strings.Contains(gate.Error(), ReasonReviewRejectRateAboveThreshold) || !strings.Contains(gate.Error(), "10.50%") {
		t.Fatalf("gate error text = %q", gate.Error())
	}
	if got := reviewRejectRateDetail(thresholdTestSource("pretrain", nil, 200, 179, 21), reasons); got != "" {
		t.Fatalf("detail without threshold = %q, want empty", got)
	}
	plain := &GateError{Reasons: []string{"rights_not_cleared"}}
	if plain.Error() != "review gate blocked: rights_not_cleared" {
		t.Fatalf("GateError text changed without detail: %q", plain.Error())
	}
}

func TestPretrainReviewThresholdChangeReasons(t *testing.T) {
	ten := floatPointer(proposedThresholdPercent)
	tests := []struct {
		name          string
		purpose       string
		reviewStarted bool
		value         *float64
		want          []string
	}{
		{"pretrain before review", "pretrain", false, ten, []string{}},
		{"clearing before review", "pretrain", false, nil, []string{}},
		{"locked after review started", "pretrain", true, ten, []string{reasonThresholdReviewLocked}},
		{"clearing is locked too", "pretrain", true, nil, []string{reasonThresholdReviewLocked}},
		{"instruction source", "instruction", false, ten, []string{reasonThresholdPurpose}},
		{"negative", "pretrain", false, floatPointer(-0.01), []string{reasonThresholdInvalid}},
		{"above 100", "pretrain", false, floatPointer(100.01), []string{reasonThresholdInvalid}},
		{"three decimals", "pretrain", false, floatPointer(10.005), []string{reasonThresholdInvalid}},
		{"two decimals", "pretrain", false, floatPointer(12.25), []string{}},
		{"zero", "pretrain", false, floatPointer(0), []string{}},
		{"hundred", "pretrain", false, floatPointer(100), []string{}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := pretrainThresholdChangeReasons(test.purpose, test.reviewStarted, test.value)
			if !reflect.DeepEqual(got, test.want) {
				t.Fatalf("pretrainThresholdChangeReasons() = %#v, want %#v", got, test.want)
			}
		})
	}
}
