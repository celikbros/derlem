package config

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Environment            string
	HTTPAddr               string
	WebOrigin              string
	DatabaseURL            string
	JWTSecret              string
	JWTIssuer              string
	JWTTTL                 time.Duration
	SessionIdleTTL         time.Duration
	LoginFailureWindow     time.Duration
	LoginLockoutDuration   time.Duration
	LoginAccountLimit      int
	LoginIPLimit           int
	BootstrapAdminEmail    string
	BootstrapAdminPassword string
	StorageRoot            string
	StagingRoot            string
	MaxUploadBytes         int64
	WorkerPollInterval     time.Duration
}

func Load() (Config, error) {
	if err := loadDotEnv(".env"); err != nil && !errors.Is(err, os.ErrNotExist) {
		return Config{}, fmt.Errorf("load .env: %w", err)
	}

	jwtTTL, err := durationEnv("JWT_TTL", 8*time.Hour)
	if err != nil {
		return Config{}, err
	}
	sessionIdleTTL, err := durationEnv("SESSION_IDLE_TTL", 30*time.Minute)
	if err != nil {
		return Config{}, err
	}
	loginFailureWindow, err := durationEnv("LOGIN_FAILURE_WINDOW", 15*time.Minute)
	if err != nil {
		return Config{}, err
	}
	loginLockoutDuration, err := durationEnv("LOGIN_LOCKOUT_DURATION", 15*time.Minute)
	if err != nil {
		return Config{}, err
	}
	workerPollInterval, err := durationEnv("WORKER_POLL_INTERVAL", 2*time.Second)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{
		Environment:            envOr("APP_ENV", "development"),
		HTTPAddr:               envOr("HTTP_ADDR", ":8080"),
		WebOrigin:              envOr("WEB_ORIGIN", "http://localhost:3000"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		JWTIssuer:              envOr("JWT_ISSUER", "derlem"),
		JWTTTL:                 jwtTTL,
		SessionIdleTTL:         sessionIdleTTL,
		LoginFailureWindow:     loginFailureWindow,
		LoginLockoutDuration:   loginLockoutDuration,
		BootstrapAdminEmail:    strings.ToLower(strings.TrimSpace(os.Getenv("BOOTSTRAP_ADMIN_EMAIL"))),
		BootstrapAdminPassword: os.Getenv("BOOTSTRAP_ADMIN_PASSWORD"),
		StorageRoot:            envOr("STORAGE_ROOT", "./var/storage"),
		StagingRoot:            envOr("STAGING_ROOT", "./var/staging"),
		WorkerPollInterval:     workerPollInterval,
	}
	cfg.MaxUploadBytes, err = int64Env("MAX_UPLOAD_BYTES", 50*1024*1024*1024)
	if err != nil {
		return Config{}, err
	}
	cfg.LoginAccountLimit, err = intEnv("LOGIN_ACCOUNT_FAILURE_LIMIT", 5)
	if err != nil {
		return Config{}, err
	}
	cfg.LoginIPLimit, err = intEnv("LOGIN_IP_FAILURE_LIMIT", 30)
	if err != nil {
		return Config{}, err
	}

	if cfg.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if len(cfg.JWTSecret) < 32 {
		return Config{}, errors.New("JWT_SECRET must contain at least 32 characters")
	}
	if cfg.JWTTTL <= 0 || cfg.SessionIdleTTL <= 0 || cfg.LoginFailureWindow <= 0 || cfg.LoginLockoutDuration <= 0 {
		return Config{}, errors.New("JWT and login/session durations must be positive")
	}
	if cfg.BootstrapAdminEmail != "" && cfg.BootstrapAdminPassword == "" {
		return Config{}, errors.New("BOOTSTRAP_ADMIN_PASSWORD is required when BOOTSTRAP_ADMIN_EMAIL is set")
	}
	if cfg.BootstrapAdminPassword != "" && len(cfg.BootstrapAdminPassword) < 12 {
		return Config{}, errors.New("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
	}

	return cfg, nil
}

func intEnv(key string, fallback int) (int, error) {
	value, err := int64Env(key, int64(fallback))
	if err != nil {
		return 0, err
	}
	if value > int64(^uint(0)>>1) {
		return 0, fmt.Errorf("parse %s: value is too large", key)
	}
	return int(value), nil
}

func int64Env(key string, fallback int64) (int64, error) {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("parse %s: must be a positive integer", key)
	}
	return parsed, nil
}

func envOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func durationEnv(key string, fallback time.Duration) (time.Duration, error) {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback, nil
	}
	duration, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", key, err)
	}
	return duration, nil
}

func loadDotEnv(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, found := strings.Cut(line, "=")
		if !found {
			return fmt.Errorf("invalid .env line %q", line)
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if len(value) >= 2 {
			if unquoted, err := strconv.Unquote(value); err == nil {
				value = unquoted
			}
		}
		if _, exists := os.LookupEnv(key); !exists {
			if err := os.Setenv(key, value); err != nil {
				return err
			}
		}
	}
	return scanner.Err()
}
