package config

import "testing"

func TestIntEnvRequiresPositiveInteger(t *testing.T) {
	const key = "DERLEM_TEST_POSITIVE_INT"
	t.Setenv(key, "12")
	if value, err := intEnv(key, 5); err != nil || value != 12 {
		t.Fatalf("unexpected positive integer result: value=%d err=%v", value, err)
	}

	t.Setenv(key, "0")
	if _, err := intEnv(key, 5); err == nil {
		t.Fatal("expected zero to fail")
	}

	t.Setenv(key, "not-a-number")
	if _, err := intEnv(key, 5); err == nil {
		t.Fatal("expected non-numeric value to fail")
	}
}

func TestIntEnvUsesFallback(t *testing.T) {
	const key = "DERLEM_TEST_POSITIVE_INT_FALLBACK"
	t.Setenv(key, "")
	if value, err := intEnv(key, 7); err != nil || value != 7 {
		t.Fatalf("unexpected fallback result: value=%d err=%v", value, err)
	}
}
