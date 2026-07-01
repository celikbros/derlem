package httpapi

import (
	"net/http/httptest"
	"testing"
	"time"
)

func TestClientIPTrustsRealIPOnlyFromLoopbackProxy(t *testing.T) {
	proxied := httptest.NewRequest("POST", "/api/v1/auth/login", nil)
	proxied.RemoteAddr = "127.0.0.1:12345"
	proxied.Header.Set("X-Real-IP", "203.0.113.10")
	if actual := clientIP(proxied); actual != "203.0.113.10" {
		t.Fatalf("unexpected proxied IP: %q", actual)
	}

	direct := httptest.NewRequest("POST", "/api/v1/auth/login", nil)
	direct.RemoteAddr = "198.51.100.20:12345"
	direct.Header.Set("X-Real-IP", "203.0.113.10")
	if actual := clientIP(direct); actual != "198.51.100.20" {
		t.Fatalf("untrusted proxy header was accepted: %q", actual)
	}
}

func TestWriteRateLimitedIncludesRetryAfter(t *testing.T) {
	response := httptest.NewRecorder()
	writeRateLimited(response, 1500*time.Millisecond)
	if response.Code != 429 || response.Header().Get("Retry-After") != "2" {
		t.Fatalf("unexpected rate-limit response: status=%d retry=%q", response.Code, response.Header().Get("Retry-After"))
	}
}
