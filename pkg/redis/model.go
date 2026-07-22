package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	// ErrNotFound is returned by Load and Delete when the key does not exist.
	ErrNotFound = errors.New("not found")
	// ErrLockBusy is returned by Lock when MaxWait is exceeded.
	ErrLockBusy = errors.New("lock busy")
)

// LockOptions parameterises the wait/retry behaviour of Model.Lock.
type LockOptions struct {
	// TTL is the self-recovery TTL applied when release fails or the holder crashes.
	TTL time.Duration
	// MaxWait is the total time the caller is willing to wait for the lock.
	MaxWait time.Duration
	// RetryDelay is the delay between SETNX attempts.
	RetryDelay time.Duration
}

// DefaultLockOptions are the recommended defaults for sub-second critical sections.
var DefaultLockOptions = LockOptions{
	TTL:        5 * time.Second,
	MaxWait:    2 * time.Second,
	RetryDelay: 25 * time.Millisecond,
}

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

// Lock acquires a distributed lock keyed off this model's identity.
// The returned release func MUST be invoked (typically via defer); the TTL
// in opts provides eventual recovery if it is not. Returns ErrLockBusy when
// MaxWait is exceeded, or the context error if the context is cancelled
// while waiting.
func (m *Model[T]) Lock(ctx context.Context, db redis.UniversalClient, opts LockOptions) (func(), error) {
	key := "lock:" + m.t.Key()
	deadline := time.Now().Add(opts.MaxWait)

	for {
		ok, err := db.SetNX(ctx, key, "", opts.TTL).Result()
		if err != nil {
			return nil, fmt.Errorf("acquire lock: %w", err)
		}

		if ok {
			break
		}

		if time.Now().After(deadline) {
			return nil, ErrLockBusy
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(opts.RetryDelay):
		}
	}

	return func() {
		_ = db.Del(context.Background(), key).Err()
	}, nil
}
