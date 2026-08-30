package repository

import "testing"

func TestTrustedPurposeContractVersionFailsClosed(t *testing.T) {
	for _, testCase := range []struct {
		name       string
		profileKey string
		version    string
		purpose    string
		wantOK     bool
	}{
		{name: "legacy pretrain", profileKey: "legacy-auto", version: "1", purpose: "pretrain", wantOK: true},
		{name: "text instruction", profileKey: "text-document", version: "1", purpose: "instruction", wantOK: true},
		{name: "unknown profile", profileKey: "translation", version: "1", purpose: "pretrain"},
		{name: "unknown version", profileKey: "text-document", version: "2", purpose: "pretrain"},
		{name: "unknown purpose", profileKey: "text-document", version: "1", purpose: "translation"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			version, ok := trustedPurposeContractVersion(
				testCase.profileKey, testCase.version, testCase.purpose,
			)
			if ok != testCase.wantOK {
				t.Fatalf("trusted = %t, want %t", ok, testCase.wantOK)
			}
			if ok && version != "1" {
				t.Fatalf("contract version = %q, want 1", version)
			}
			if !ok && version != "" {
				t.Fatalf("untrusted contract returned version %q", version)
			}
		})
	}
}

func TestTrustedProfileImplementationKeyFailsClosed(t *testing.T) {
	for _, testCase := range []struct {
		profileKey string
		wantKey    string
		wantOK     bool
	}{
		{profileKey: "legacy-auto", wantKey: "legacy-current-v1", wantOK: true},
		{profileKey: "text-document", wantKey: "text-document-v1", wantOK: true},
		{profileKey: "translation"},
	} {
		key, ok := trustedProfileImplementationKey(testCase.profileKey)
		if ok != testCase.wantOK || key != testCase.wantKey {
			t.Fatalf(
				"trustedProfileImplementationKey(%q) = %q, %t; want %q, %t",
				testCase.profileKey, key, ok, testCase.wantKey, testCase.wantOK,
			)
		}
	}
}
