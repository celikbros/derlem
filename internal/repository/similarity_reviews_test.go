package repository

import (
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestValidateSimilarityPairReview(t *testing.T) {
	reason := "Daha fazla alan bilgisi gerekiyor."
	longReason := string(make([]rune, 2001))
	tests := []struct {
		name  string
		input domain.ReviewSimilarityPairInput
		want  string
	}{
		{name: "exact", input: domain.ReviewSimilarityPairInput{Label: "exact_duplicate"}},
		{name: "near", input: domain.ReviewSimilarityPairInput{Label: "near_duplicate"}},
		{name: "related", input: domain.ReviewSimilarityPairInput{Label: "related"}},
		{name: "different", input: domain.ReviewSimilarityPairInput{Label: "different"}},
		{name: "uncertain with reason", input: domain.ReviewSimilarityPairInput{Label: "uncertain", Reason: &reason}},
		{name: "uncertain needs reason", input: domain.ReviewSimilarityPairInput{Label: "uncertain"}, want: "reason_required"},
		{name: "unknown", input: domain.ReviewSimilarityPairInput{Label: "same"}, want: "invalid_similarity_label"},
		{name: "reason limit", input: domain.ReviewSimilarityPairInput{Label: "related", Reason: &longReason}, want: "reason_too_long"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := ValidateSimilarityPairReview(test.input); got != test.want {
				t.Fatalf("ValidateSimilarityPairReview() = %q, want %q", got, test.want)
			}
		})
	}
}
