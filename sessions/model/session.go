package model

import (
	"context"
	"fmt"
	"time"

	pkgRedis "gitlab.com/isard/isardvdi/pkg/redis"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type Session struct {
	// ID is the session ID
	ID         string       `json:"id"`
	UserID     string       `json:"user_id"`
	RemoteAddr string       `json:"remote_addr"`
	Time       *SessionTime `json:"time"`
}

// SessionTime contains all the information related with the lifespan of the session
type SessionTime struct {
	// MaxTime is the time when the session will expire and won't be able to be renewed
	MaxTime time.Time `json:"max_time"`
	//  MaxRenewTime is the time when the session won't be able to be renewed
	MaxRenewTime time.Time `json:"max_renew_time"`
	// ExpirationTime is the time when the session will expire if it's not renewed
	ExpirationTime time.Time `json:"expiration_time"`
}

func NewSession(ctx context.Context, db redis.UniversalClient, userID, RemoteAddr string, time *SessionTime) (*Session, error) {
	s := &Session{
		ID:         uuid.NewString(),
		UserID:     userID,
		RemoteAddr: RemoteAddr,
		Time:       time,
	}

	if err := s.Update(ctx, db); err != nil {
		return nil, fmt.Errorf("save session: %w", err)
	}

	return s, nil
}

const sessionKeyPrefix = "session:"

func (s Session) Key() string {
	return sessionKeyPrefix + s.ID
}

func (s Session) Expiration() time.Duration {
	return time.Until(s.Time.MaxTime)
}

func (s *Session) Load(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.NewModel(s).Load(ctx, db)
}

func (s *Session) Update(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.NewModel(s).Update(ctx, db)
}

func (s *Session) Delete(ctx context.Context, db redis.UniversalClient) error {
	return pkgRedis.NewModel(s).Delete(ctx, db)
}
