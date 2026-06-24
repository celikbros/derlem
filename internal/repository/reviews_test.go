package repository

import (
	"reflect"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestApprovalGateReasons(t *testing.T) {
	digest := "0123456789012345678901234567890123456789012345678901234567890123"
	evidence := "license/evidence"

	tests := []struct {
		name   string
		source domain.Source
		want   []string
	}{
		{
			name: "all gates pass",
			source: domain.Source{
				ObjectSHA256: &digest, RightsStatus: "cleared", LicenseEvidenceRef: &evidence,
				PIIStatus: "clear", ApprovalStatus: "auto_checked",
			},
			want: []string{},
		},
		{
			name:   "all mandatory gates fail",
			source: domain.Source{RightsStatus: "unknown", PIIStatus: "not_scanned", ApprovalStatus: "source_registered"},
			want:   []string{"file_not_ingested", "rights_not_cleared", "license_evidence_missing", "pii_not_clear"},
		},
		{
			name: "already approved",
			source: domain.Source{
				ObjectSHA256: &digest, RightsStatus: "cleared", LicenseEvidenceRef: &evidence,
				PIIStatus: "clear", ApprovalStatus: "approved_source",
			},
			want: []string{"already_approved"},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := approvalGateReasons(test.source); !reflect.DeepEqual(got, test.want) {
				t.Fatalf("approvalGateReasons() = %#v, want %#v", got, test.want)
			}
		})
	}
}
