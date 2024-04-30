package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
)

var ErrNotFound = errors.New("not found")

type Modelable interface {
	Key() string
	Expiration() time.Duration
}

func Load(ctx context.Context, db redis.UniversalClient, m Modelable) error {
	b, err := db.Get(ctx, m.Key()).Bytes()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return ErrNotFound
		}

		return fmt.Errorf("get: %w", err)
	}

	log.Println(string(b))

	if err := json.Unmarshal(b, m); err != nil {
		return fmt.Errorf("unmarshal from JSON: %w", err)
	}

	log.Fatalf("%+v", m)

	return nil
}

func Update(ctx context.Context, db redis.UniversalClient, m Modelable) error {
	b, err := json.Marshal(m)
	if err != nil {
		return fmt.Errorf("marshal to JSON: %w", err)
	}

	if err := db.Set(ctx, m.Key(), b, m.Expiration()).Err(); err != nil {
		return fmt.Errorf("update: %w", err)
	}

	return nil
}

func Delete(ctx context.Context, db redis.UniversalClient, m Modelable) error {
	del, err := db.Del(ctx, m.Key()).Result()
	if err != nil {
		return fmt.Errorf("delete: %w", err)
	}

	if del == 0 {
		return ErrNotFound
	}

	return nil
}
