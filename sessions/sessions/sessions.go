package sessions

import (
	"context"
	"errors"
	"fmt"
	"net"
	"time"

	pkgRedis "gitlab.com/isard/isardvdi/pkg/redis"
	"gitlab.com/isard/isardvdi/sessions/cfg"
	"gitlab.com/isard/isardvdi/sessions/model"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

var (
	ErrSessionExpired     = errors.New("session expired")
	ErrRenewTimeExpired   = errors.New("renew time has expired")
	ErrMaxSessionTime     = errors.New("max session time reached")
	ErrMissingUserID      = errors.New("missing user ID")
	ErrInvalidRemoteAddr  = errors.New("invalid remote address")
	ErrRemoteAddrMismatch = errors.New("remote address mismatch")
)

type Interface interface {
	New(ctx context.Context, userID string, remoteAddr string) (*model.Session, error)
	Get(ctx context.Context, id string, remoteAddr string) (*model.Session, error)
	GetUserSession(ctx context.Context, userID string) (*model.Session, error)
	Renew(ctx context.Context, id string, remoteAddr string) (*model.SessionTime, error)
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

func (s *Sessions) New(ctx context.Context, userID string, remoteAddr string) (*model.Session, error) {
	if userID == "" {
		return nil, ErrMissingUserID
	}

	parsedRemoteAddr := net.ParseIP(remoteAddr)
	if parsedRemoteAddr == nil {
		return nil, ErrInvalidRemoteAddr
	}

	now := time.Now()
	time := &model.SessionTime{
		MaxTime:        now.Add(s.Cfg.MaxTime),
		MaxRenewTime:   now.Add(s.Cfg.MaxRenewTime),
		ExpirationTime: now.Add(s.Cfg.ExpirationTime),
	}

	usr := &model.User{ID: userID}
	if err := usr.Load(ctx, s.redis); err != nil {
		if !errors.Is(err, pkgRedis.ErrNotFound) {
			return nil, fmt.Errorf("load user: %w", err)
		}

	} else {
		// If there's already a user with an active session, revoke the existing
		// session to ensure there's only one active session per user
		if err := s.Revoke(ctx, usr.SessionID); err != nil {
			if errors.Is(err, pkgRedis.ErrNotFound) {
				// If the session is not found, we can delete the user
				if err := usr.Delete(ctx, s.redis); err != nil {
					return nil, fmt.Errorf("delete user: %w", err)
				}
			} else {
				return nil, fmt.Errorf("revoke old user session: %w", err)
			}
		}
	}

	sess, err := model.NewSession(ctx, s.redis, userID, parsedRemoteAddr.String(), time)
	if err != nil {
		return nil, fmt.Errorf("create new session: %w", err)
	}

	if _, err := model.NewUser(ctx, s.redis, userID, sess.ID, sess.Time.MaxTime); err != nil {
		return nil, fmt.Errorf("create new user: %w", err)
	}

	return sess, nil
}

func (s *Sessions) Get(ctx context.Context, id, remoteAddr string) (*model.Session, error) {
	if id == "isardvdi-service" {
		now := time.Now()
		return &model.Session{
			ID: "isardvdi-service",
			Time: &model.SessionTime{
				MaxTime:        now.Add(20 * time.Second),
				MaxRenewTime:   now.Add(20 * time.Second),
				ExpirationTime: now.Add(20 * time.Second),
			},
		}, nil
	}

	parsedRemoteAddr := net.ParseIP(remoteAddr)
	if parsedRemoteAddr == nil {
		return nil, ErrInvalidRemoteAddr
	}

	sess := &model.Session{ID: id}
	if err := sess.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load session: %w", err)
	}

	if s.Cfg.RemoteAddrControl {
		if sess.RemoteAddr != parsedRemoteAddr.String() {
			return nil, ErrRemoteAddrMismatch
		}
	}

	if sess.Time.ExpirationTime.Before(time.Now()) {
		return nil, ErrSessionExpired
	}

	return sess, nil
}

func (s *Sessions) GetUserSession(ctx context.Context, userID string) (*model.Session, error) {
	if userID == "" {
		return nil, ErrMissingUserID
	}

	usr := &model.User{ID: userID}
	if err := usr.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load user: %w", err)
	}

	sess := &model.Session{ID: usr.SessionID}
	if err := sess.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load session: %w", err)
	}

	return sess, nil
}

func (s *Sessions) Renew(ctx context.Context, id, remoteAddr string) (*model.SessionTime, error) {
	parsedRemoteAddr := net.ParseIP(remoteAddr)
	if parsedRemoteAddr == nil {
		return nil, ErrInvalidRemoteAddr
	}

	sess := &model.Session{ID: id}
	if err := sess.Load(ctx, s.redis); err != nil {
		return nil, fmt.Errorf("load session: %w", err)
	}

	if s.Cfg.RemoteAddrControl {
		if sess.RemoteAddr != parsedRemoteAddr.String() {
			return nil, ErrRemoteAddrMismatch
		}
	}

	now := time.Now()
	if sess.Time.MaxRenewTime.Before(now) {
		return nil, ErrRenewTimeExpired
	}

	if sess.Time.MaxTime.Before(now.Add(s.Cfg.ExpirationTime)) {
		return nil, ErrMaxSessionTime
	}

	sess.Time.ExpirationTime = now.Add(s.Cfg.ExpirationTime)

	if sess.Time.MaxRenewTime.Add(s.Cfg.MaxRenewTime).After(sess.Time.MaxTime) {
		sess.Time.MaxRenewTime = sess.Time.MaxTime

	} else {
		sess.Time.MaxRenewTime = now.Add(s.Cfg.MaxRenewTime)
	}

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

	usr := &model.User{ID: sess.UserID}
	if err := usr.Load(ctx, s.redis); err != nil {
		return fmt.Errorf("load user: %w", err)
	}
	if err := usr.Delete(ctx, s.redis); err != nil {
		return fmt.Errorf("delete user: %w", err)
	}

	return nil
}
