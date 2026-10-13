package httpapi

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestHFImportIsAdminOnly(t *testing.T) {
	const pattern = "POST /api/v1/sources/import-hf"
	for _, route := range protectedRoutes(&Server{}) {
		if route.pattern != pattern {
			continue
		}
		if !slices.Equal(route.roles, []string{roleAdmin}) {
			t.Fatalf("hf import roles = %v, want admin only", route.roles)
		}
		for _, role := range applicationRoles {
			assertRoleAccess(t, route.roles, role, role == roleAdmin)
		}
		return
	}
	t.Fatalf("route %q not found", pattern)
}

func hfImportRoots(t *testing.T) (string, string, string) {
	t.Helper()
	base := t.TempDir()
	importRoot := filepath.Join(base, "import")
	adaptersRoot := filepath.Join(base, "adapters")
	for _, dir := range []string{importRoot, adaptersRoot} {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			t.Fatal(err)
		}
	}
	adapter := filepath.Join(adaptersRoot, "epfml-fineweb2-hq.yaml")
	if err := os.WriteFile(adapter, []byte("dataset: x\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(base, "outside.yaml"), []byte("dataset: x\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(adaptersRoot, "notes.txt"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	return importRoot, adaptersRoot, adapter
}

func TestResolveAdapterPathStaysUnderRoots(t *testing.T) {
	importRoot, adaptersRoot, adapter := hfImportRoots(t)
	resolvedAdapter, _ := filepath.EvalSymlinks(adapter)
	for _, candidate := range []string{adapter, "epfml-fineweb2-hq.yaml"} {
		resolved, err := resolveAdapterPath(importRoot, adaptersRoot, candidate)
		if err != nil {
			t.Fatalf("%q: unexpected error %v", candidate, err)
		}
		if resolved != resolvedAdapter {
			t.Fatalf("%q resolved to %q, want %q", candidate, resolved, resolvedAdapter)
		}
	}
	outside := filepath.Join(filepath.Dir(adaptersRoot), "outside.yaml")
	for _, candidate := range []string{
		"", outside, "../outside.yaml", filepath.Join(adaptersRoot, "..", "outside.yaml"),
		filepath.Join(adaptersRoot, "notes.txt"), "missing.yaml",
	} {
		if _, err := resolveAdapterPath(importRoot, adaptersRoot, candidate); err == nil {
			t.Fatalf("%q: expected rejection", candidate)
		}
	}
}

func TestHFImportValidation(t *testing.T) {
	ref := "docs/haklar/hf-fineweb2-hq.md"
	input, _, message := hfImportSourceInput(hfImportRequest{
		ContentPurpose: "pretrain", RightsStatus: "restricted", LicenseEvidenceRef: &ref,
	}, "/x/adapters/epfml-fineweb2-hq.yaml")
	if message != "" {
		t.Fatalf("unexpected validation failure: %s", message)
	}
	if input.SourceType != "hf_dataset" || input.Name != "HF: epfml-fineweb2-hq" || input.License != hfPendingLicense || input.Language != "tr" {
		t.Fatalf("unexpected source input: %#v", input)
	}
	if !strings.Contains(input.LineageRef, "epfml-fineweb2-hq.yaml") {
		t.Fatalf("lineage placeholder lacks adapter: %q", input.LineageRef)
	}

	bad := "../secret.md"
	outside := "notes/x.md"
	long := strings.Repeat("a", hfMaxLineageNote+1)
	cases := []hfImportRequest{
		{ContentPurpose: "model-specific", RightsStatus: "unknown"},
		{ContentPurpose: "pretrain", RightsStatus: "maybe"},
		{ContentPurpose: "pretrain", RightsStatus: "cleared"},
		{ContentPurpose: "pretrain", RightsStatus: "unknown", LicenseEvidenceRef: &bad},
		{ContentPurpose: "pretrain", RightsStatus: "unknown", LicenseEvidenceRef: &outside},
		{ContentPurpose: "pretrain", RightsStatus: "unknown", LineageNote: &long},
	}
	for index, request := range cases {
		if _, _, message := hfImportSourceInput(request, "/x/a.yaml"); message == "" {
			t.Fatalf("case %d: expected validation failure", index)
		}
	}
}

func TestHFImportHandlerRejectsBeforeQueueing(t *testing.T) {
	importRoot, adaptersRoot, _ := hfImportRoots(t)
	server := (&Server{importRoot: importRoot}).WithAdaptersRoot(adaptersRoot)
	cases := map[string]struct {
		body string
		code int
	}{
		"unknown field":  {`{"adapter_path":"epfml-fineweb2-hq.yaml","content_purpose":"pretrain","rights_status":"unknown","revision":"main"}`, http.StatusBadRequest},
		"two objects":    {`{"adapter_path":"a.yaml"}{}`, http.StatusBadRequest},
		"escaping path":  {`{"adapter_path":"../outside.yaml","content_purpose":"pretrain","rights_status":"unknown"}`, http.StatusUnprocessableEntity},
		"bad purpose":    {`{"adapter_path":"epfml-fineweb2-hq.yaml","content_purpose":"x","rights_status":"unknown"}`, http.StatusUnprocessableEntity},
		"cleared no ref": {`{"adapter_path":"epfml-fineweb2-hq.yaml","content_purpose":"pretrain","rights_status":"cleared"}`, http.StatusUnprocessableEntity},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, "/api/v1/sources/import-hf", strings.NewReader(tc.body))
			recorder := httptest.NewRecorder()
			server.importHFDataset(recorder, request)
			if recorder.Code != tc.code {
				t.Fatalf("status = %d, want %d (%s)", recorder.Code, tc.code, recorder.Body.String())
			}
		})
	}
}
