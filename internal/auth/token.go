package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

var rawURL = base64.RawURLEncoding

type Claims struct {
	Subject     string   `json:"sub"`
	Email       string   `json:"email"`
	Roles       []string `json:"roles"`
	JWTID       string   `json:"jti"`
	AuthVersion int64    `json:"auth_version"`
	Issuer      string   `json:"iss"`
	IssuedAt    int64    `json:"iat"`
	ExpiresAt   int64    `json:"exp"`
}

type TokenManager struct {
	secret []byte
	issuer string
	ttl    time.Duration
	now    func() time.Time
}

func NewTokenManager(secret, issuer string, ttl time.Duration) *TokenManager {
	return &TokenManager{
		secret: []byte(secret),
		issuer: issuer,
		ttl:    ttl,
		now:    time.Now,
	}
}

func (m *TokenManager) Issue(userID, email string, roles []string, jwtID string, authVersion int64) (string, time.Time, error) {
	if strings.TrimSpace(jwtID) == "" || authVersion <= 0 {
		return "", time.Time{}, errors.New("session identity and auth version are required")
	}
	now := m.now().UTC()
	expiresAt := now.Add(m.ttl)
	header := map[string]string{"alg": "HS256", "typ": "JWT"}
	claims := Claims{
		Subject:     userID,
		Email:       email,
		Roles:       roles,
		JWTID:       jwtID,
		AuthVersion: authVersion,
		Issuer:      m.issuer,
		IssuedAt:    now.Unix(),
		ExpiresAt:   expiresAt.Unix(),
	}

	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", time.Time{}, err
	}
	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		return "", time.Time{}, err
	}
	unsigned := rawURL.EncodeToString(headerJSON) + "." + rawURL.EncodeToString(claimsJSON)
	signature := m.sign(unsigned)
	return unsigned + "." + signature, expiresAt, nil
}

func (m *TokenManager) Parse(token string) (Claims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return Claims{}, errors.New("malformed token")
	}
	if !hmac.Equal([]byte(parts[2]), []byte(m.sign(parts[0]+"."+parts[1]))) {
		return Claims{}, errors.New("invalid token signature")
	}

	headerJSON, err := rawURL.DecodeString(parts[0])
	if err != nil {
		return Claims{}, errors.New("invalid token header")
	}
	var header map[string]string
	if err := json.Unmarshal(headerJSON, &header); err != nil || header["alg"] != "HS256" {
		return Claims{}, errors.New("unsupported token algorithm")
	}

	claimsJSON, err := rawURL.DecodeString(parts[1])
	if err != nil {
		return Claims{}, errors.New("invalid token claims")
	}
	var claims Claims
	if err := json.Unmarshal(claimsJSON, &claims); err != nil {
		return Claims{}, errors.New("invalid token claims")
	}
	if claims.Issuer != m.issuer || claims.Subject == "" || claims.JWTID == "" || claims.AuthVersion <= 0 {
		return Claims{}, errors.New("invalid token issuer or subject")
	}
	if claims.IssuedAt <= 0 || claims.ExpiresAt <= claims.IssuedAt {
		return Claims{}, errors.New("invalid token lifetime")
	}
	if m.now().UTC().Unix() >= claims.ExpiresAt {
		return Claims{}, errors.New("token expired")
	}
	return claims, nil
}

func (m *TokenManager) sign(value string) string {
	mac := hmac.New(sha256.New, m.secret)
	mac.Write([]byte(value))
	return rawURL.EncodeToString(mac.Sum(nil))
}

func BearerToken(header string) (string, error) {
	scheme, token, found := strings.Cut(strings.TrimSpace(header), " ")
	if !found || !strings.EqualFold(scheme, "Bearer") || strings.TrimSpace(token) == "" {
		return "", errors.New("bearer token required")
	}
	return strings.TrimSpace(token), nil
}

func ParsePositiveInt(value string, fallback, maximum int) (int, error) {
	if strings.TrimSpace(value) == "" {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("must be a positive integer")
	}
	if parsed > maximum {
		return maximum, nil
	}
	return parsed, nil
}
