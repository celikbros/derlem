package httpapi

import "testing"

func TestSanitizeUploadFilename(t *testing.T) {
	tests := map[string]string{
		`C:\users\alice\corpus.jsonl`: "corpus.jsonl",
		"../corpus.txt":               "corpus.txt",
		"bad\x00name.txt":             "badname.txt",
		"":                            "upload.bin",
	}
	for input, want := range tests {
		if got := sanitizeUploadFilename(input); got != want {
			t.Fatalf("sanitizeUploadFilename(%q) = %q, want %q", input, got, want)
		}
	}
}
