package auth

import (
	"encoding/hex"
	"testing"
)

func TestSessionIDIsRandomAndHashable(t *testing.T) {
	first, err := NewSessionID()
	if err != nil {
		t.Fatal(err)
	}
	second, err := NewSessionID()
	if err != nil {
		t.Fatal(err)
	}
	if first == second || len(first) < 40 {
		t.Fatalf("unexpected session ids: %q %q", first, second)
	}
	digest := SessionIDHash(first)
	if len(digest) != 64 {
		t.Fatalf("unexpected digest length: %d", len(digest))
	}
	if _, err := hex.DecodeString(digest); err != nil {
		t.Fatalf("session digest is not hexadecimal: %v", err)
	}
}

func TestLoginRateKeysDoNotContainRawValues(t *testing.T) {
	limiter := NewLoginLimiter(nil, LoginRatePolicy{}, "01234567890123456789012345678901")
	keys := limiter.Keys("admin@example.com", "127.0.0.1")
	if keys.Account == keys.IP || len(keys.Account) != 64 || len(keys.IP) != 64 {
		t.Fatalf("unexpected login rate keys: %#v", keys)
	}
	if keys.Account == "admin@example.com" || keys.IP == "127.0.0.1" {
		t.Fatal("raw login identifiers must not be stored")
	}
	otherKey := NewLoginLimiter(nil, LoginRatePolicy{}, "different-secret-0123456789012345").Keys("admin@example.com", "127.0.0.1")
	if keys == otherKey {
		t.Fatal("login rate keys must be bound to the server secret")
	}
}
