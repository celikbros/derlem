package database

import (
	"context"
	"crypto/sha256"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

func Migrate(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version text PRIMARY KEY,
			checksum text,
			applied_at timestamptz NOT NULL DEFAULT now()
		);
		ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum text
	`); err != nil {
		return fmt.Errorf("create schema_migrations: %w", err)
	}

	entries, err := fs.ReadDir(migrationFiles, "migrations")
	if err != nil {
		return fmt.Errorf("read migrations: %w", err)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })

	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}

		contents, err := migrationFiles.ReadFile("migrations/" + entry.Name())
		if err != nil {
			return fmt.Errorf("read migration %s: %w", entry.Name(), err)
		}
		checksum := fmt.Sprintf("%x", sha256.Sum256(contents))
		var appliedChecksum *string
		err = pool.QueryRow(ctx,
			"SELECT checksum FROM schema_migrations WHERE version = $1",
			entry.Name(),
		).Scan(&appliedChecksum)
		if err == nil {
			if appliedChecksum == nil {
				if _, err := pool.Exec(ctx,
					"UPDATE schema_migrations SET checksum = $2 WHERE version = $1 AND checksum IS NULL",
					entry.Name(), checksum,
				); err != nil {
					return fmt.Errorf("backfill migration checksum %s: %w", entry.Name(), err)
				}
				continue
			}
			if *appliedChecksum != checksum {
				return fmt.Errorf(
					"migration checksum mismatch for %s: database=%s embedded=%s",
					entry.Name(), *appliedChecksum, checksum,
				)
			}
			continue
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return fmt.Errorf("check migration %s: %w", entry.Name(), err)
		}

		tx, err := pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration %s: %w", entry.Name(), err)
		}
		if _, err := tx.Exec(ctx, string(contents)); err != nil {
			tx.Rollback(ctx)
			return fmt.Errorf("apply migration %s: %w", entry.Name(), err)
		}
		if _, err := tx.Exec(ctx,
			"INSERT INTO schema_migrations(version, checksum) VALUES ($1, $2)",
			entry.Name(), checksum,
		); err != nil {
			tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", entry.Name(), err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", entry.Name(), err)
		}
	}

	return nil
}
