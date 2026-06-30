package httpapi

import (
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestBlindSimilarityPairUntilReviewerDecision(t *testing.T) {
	consensus := "near_duplicate"
	pair := domain.SimilarityReviewPair{
		ReviewCount: 2, ConsensusLabel: &consensus, HasDisagreement: true,
	}

	blinded := blindSimilarityPair(pair, []string{"moderator"})
	if blinded.ReviewCount != 0 || blinded.ConsensusLabel != nil || blinded.HasDisagreement {
		t.Fatalf("expected reviewer evidence to be blinded: %#v", blinded)
	}

	current := "different"
	pair.CurrentReviewerLabel = &current
	revealed := blindSimilarityPair(pair, []string{"moderator"})
	if revealed.ReviewCount != 2 || revealed.ConsensusLabel == nil || !revealed.HasDisagreement {
		t.Fatalf("expected reviewed evidence to be visible: %#v", revealed)
	}

	pair.CurrentReviewerLabel = nil
	readOnly := blindSimilarityPair(pair, []string{"consumer_team"})
	if readOnly.ReviewCount != 2 || readOnly.ConsensusLabel == nil || !readOnly.HasDisagreement {
		t.Fatalf("expected read-only evidence to be visible: %#v", readOnly)
	}
}
