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
	return pkgRedis.Load(ctx, db, u)
}

func (u *User) Update(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.Update(ctx, db, u)
}

func (u *User) Delete(ctx context.Context, db redis.UniversalClient) error {

	return pkgRedis.Delete(ctx, db, u)
}
