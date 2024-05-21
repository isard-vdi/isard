package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

var ErrNotFound = errors.New("not found")

type Modelable interface {
	Key() string
	Expiration() time.Duration
}

// Model creates a CRUD layer for the underlying type
type Model[T Modelable] struct{ t T }

func NewModel[T Modelable](v T) *Model[T] {
	return &Model[T]{v}
}

func (m *Model[T]) Load(ctx context.Context, db redis.UniversalClient) error {
	b, err := db.Get(ctx, m.t.Key()).Bytes()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return ErrNotFound
		}

		return fmt.Errorf("get: %w", err)
	}

	if err := json.Unmarshal(b, m.t); err != nil {
		return fmt.Errorf("unmarshal from JSON: %w", err)
	}

	return nil
}

func (m *Model[T]) Update(ctx context.Context, db redis.UniversalClient) error {
	b, err := json.Marshal(m.t)
	if err != nil {
		return fmt.Errorf("marshal to JSON: %w", err)
	}

	if err := db.Set(ctx, m.t.Key(), b, m.t.Expiration()).Err(); err != nil {
		return fmt.Errorf("update: %w", err)
	}

	return nil
}

func (m *Model[T]) Delete(ctx context.Context, db redis.UniversalClient) error {
	del, err := db.Del(ctx, m.t.Key()).Result()
	if err != nil {
		return fmt.Errorf("delete: %w", err)
	}

	if del == 0 {
		return ErrNotFound
	}

	return nil
}
