package httpapi

import "testing"

func TestSafeDownloadName(t *testing.T) {
	tests := map[string]string{
		"Türkçe instruction/v1.json": "Türkçe-instruction-v1.json",
		"  ..\\..\\secret  ":         "secret",
		"":                           "derlem-artifact",
	}
	for input, expected := range tests {
		if actual := safeDownloadName(input); actual != expected {
			t.Fatalf("safeDownloadName(%q) = %q, want %q", input, actual, expected)
		}
	}
}
