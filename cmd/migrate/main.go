package main

import (
	"context"
	"log"

	"github.com/celikbros/derlem/internal/config"
	"github.com/celikbros/derlem/internal/database"
)

func main() {
	ctx := context.Background()
	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}
	pool, err := database.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer pool.Close()

	if err := database.Migrate(ctx, pool); err != nil {
		log.Fatal(err)
	}
	log.Println("database migrations applied")
}
