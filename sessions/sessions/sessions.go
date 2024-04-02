package sessions

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/sessions/cfg"
	"gitlab.com/isard/isardvdi/sessions/model"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

var (
	ErrSessionExpired   = errors.New("session expired")
	ErrRenewTimeExpired = errors.New("renew time has expired")
	ErrMaxSessionTime   = errors.New("max session time reached")
)

type Interface interface {
	New(ctx context.Context) (*model.Session, error)
	Get(ctx context.Context, id string) (*model.Session, error)
	Renew(ctx context.Context, id string) (*model.SessionTime, error)
	Revoke(ctx context.Context, id string) error
}

var _ Interface = &Sessions{}

type Sessions struct {
	Cfg   cfg.Sessions
	redis redis.UniversalClient
}

func Init(ctx context.Context, log *zerolog.Logger, cfg cfg.Sessions, redis redis.UniversalClient) *Sessions {
	return &Sessions{
		Cfg:   cfg,
		redis: redis,
	}
}

func (s *Sessions) New(ctx context.Context) (*model.Session, error) {
	now := time.Now()
	time := &model.SessionTime{
		MaxTime:        now.Add(s.Cfg.MaxTime),
		MaxRenewTime:   now.Add(s.Cfg.MaxRenewTime),
		ExpirationTime: now.Add(s.Cfg.ExpirationTime),
	}

	sess, err := model.NewSession(ctx, s.redis, time)
	if err != nil {
		return nil, fmt.Errorf("create new session: %w", err)
	}

	return sess, nil
}

func (s *Sessions) Get(ctx context.Context, id string) (*model.Session, error) {
	sess := &model.Session{ID: id}
	if err := sess.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load session: %w", err)
	}

	if sess.Time.ExpirationTime.Before(time.Now()) {
		return nil, ErrSessionExpired
	}

	return sess, nil
}

func (s *Sessions) Renew(ctx context.Context, id string) (*model.SessionTime, error) {
	sess := &model.Session{ID: id}
	if err := sess.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load session: %w", err)
	}

	now := time.Now()
	if sess.Time.MaxRenewTime.Before(now) {
		return nil, ErrRenewTimeExpired
	}

	if sess.Time.MaxTime.Before(now.Add(s.Cfg.ExpirationTime)) {
		return nil, ErrMaxSessionTime
	}

	sess.Time.ExpirationTime = now.Add(s.Cfg.ExpirationTime)
	sess.Time.MaxRenewTime = now.Add(s.Cfg.MaxRenewTime)

	if err := sess.Update(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("update the renewed session: %w", err)
	}

	return sess.Time, nil
}

func (s *Sessions) Revoke(ctx context.Context, id string) error {
	sess := &model.Session{ID: id}
	if err := sess.Load(ctx, s.redis); err != nil {
		return fmt.Errorf("load session: %w", err)
	}

	if err := sess.Delete(ctx, s.redis); err != nil {
		return fmt.Errorf("delete session: %w", err)
	}

	return nil
}
