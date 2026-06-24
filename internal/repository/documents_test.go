package repository

import "testing"

func TestDocumentPreview(t *testing.T) {
	preview := DocumentPreview("  birinci\n\nikinci   üçüncü  ")
	if preview != "birinci ikinci üçüncü" {
		t.Fatalf("DocumentPreview() = %q", preview)
	}

	long := make([]rune, 300)
	for index := range long {
		long[index] = 'a'
	}
	preview = DocumentPreview(string(long))
	if len([]rune(preview)) != 241 || []rune(preview)[240] != '…' {
		t.Fatalf("long preview was not rune-safe: length=%d", len([]rune(preview)))
	}
}
