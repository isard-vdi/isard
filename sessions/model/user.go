package model

import (
	"context"
	"fmt"
	"time"

	pkgRedis "gitlab.com/isard/isardvdi/pkg/redis"

	"github.com/redis/go-redis/v9"
)

type User struct {
	ID        string `json:"id"`
	SessionID string `json:"session_id"`

	expiration time.Time `json:"-"`
}

func NewUser(ctx context.Context, db redis.UniversalClient, id string, sessID string, expiration time.Time) (*User, error) {
	u := &User{
		ID:        id,
		SessionID: sessID,

		expiration: expiration,
	}

	if err := u.Update(ctx, db); err != nil {
		return nil, fmt.Errorf("save user: %w", err)
	}

	return u, nil
}

const userKeyPrefix = "user:"

func (u User) Key() string {
	return userKeyPrefix + u.ID
}

func (u User) Expiration() time.Duration {
	return time.Until(u.expiration)
}

func (u *User) Load(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.NewModel(u).Load(ctx, db)
}

func (u *User) Update(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.NewModel(u).Update(ctx, db)
}

func (u *User) Delete(ctx context.Context, db redis.UniversalClient) error {

	return pkgRedis.NewModel(u).Delete(ctx, db)
}

// Lock acquires a per-user lock with the supplied options. The returned
// release func MUST be invoked (typically via defer) to release the lock;
// the TTL in opts provides eventual recovery if it is not.
func (u *User) Lock(ctx context.Context, db redis.UniversalClient, opts pkgRedis.LockOptions) (func(), error) {
	return pkgRedis.NewModel(u).Lock(ctx, db, opts)
}
