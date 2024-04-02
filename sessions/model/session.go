package model

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

var ErrNotFound = errors.New("session not found")

type Session struct {
	// ID is the session ID
	ID   string       `json:"id"`
	Time *SessionTime `json:"time"`
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

const sessionKeyPrefix = "session:"

func sessionKey(id string) string {
	return sessionKeyPrefix + id
}

func NewSession(ctx context.Context, db redis.UniversalClient, time *SessionTime) (*Session, error) {
	s := &Session{
		ID:   uuid.NewString(),
		Time: time,
	}

	if err := s.Update(ctx, db); err != nil {
		return nil, fmt.Errorf("save session: %w", err)
	}

	return s, nil
}

func (s *Session) Load(ctx context.Context, db redis.UniversalClient) error {
	b, err := db.Get(ctx, sessionKey(s.ID)).Bytes()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return ErrNotFound
		}

		return fmt.Errorf("get session: %w", err)
	}

	if err := json.Unmarshal(b, &s); err != nil {
		return fmt.Errorf("unmarshal session from json: %w", err)
	}

	return nil
}

func (s *Session) Update(ctx context.Context, db redis.UniversalClient) error {
	b, err := json.Marshal(s)
	if err != nil {
		return fmt.Errorf("marshal session to json: %w", err)
	}

	if err := db.Set(ctx, sessionKey(s.ID), b, time.Until(s.Time.MaxTime)).Err(); err != nil {
		return fmt.Errorf("update session: %w", err)
	}

	return nil
}

func (s *Session) Delete(ctx context.Context, db redis.UniversalClient) error {
	del, err := db.Del(ctx, sessionKey(s.ID)).Result()
	if err != nil {
		return fmt.Errorf("delete session: %w", err)
	}

	if del == 0 {
		return ErrNotFound
	}

	return nil
}
