package auth

import (
	"testing"
	"time"
)

func TestTokenRoundTripAndExpiry(t *testing.T) {
	manager := NewTokenManager("01234567890123456789012345678901", "derlem-test", time.Hour)
	now := time.Date(2026, 6, 23, 12, 0, 0, 0, time.UTC)
	manager.now = func() time.Time { return now }

	token, expiresAt, err := manager.Issue("user-id", "admin@example.com", []string{"admin"})
	if err != nil {
		t.Fatal(err)
	}
	if !expiresAt.Equal(now.Add(time.Hour)) {
		t.Fatalf("unexpected expiry: %s", expiresAt)
	}
	claims, err := manager.Parse(token)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != "user-id" || claims.Email != "admin@example.com" || len(claims.Roles) != 1 {
		t.Fatalf("unexpected claims: %#v", claims)
	}

	manager.now = func() time.Time { return now.Add(time.Hour) }
	if _, err := manager.Parse(token); err == nil {
		t.Fatal("expected expired token to fail")
	}
}

func TestTokenRejectsTampering(t *testing.T) {
	manager := NewTokenManager("01234567890123456789012345678901", "derlem-test", time.Hour)
	token, _, err := manager.Issue("user-id", "admin@example.com", []string{"admin"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Parse(token + "x"); err == nil {
		t.Fatal("expected tampered token to fail")
	}
}
