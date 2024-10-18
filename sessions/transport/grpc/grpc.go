package grpc

import (
	"context"
	"errors"
	"fmt"
	"sync"

	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/redis"
	"gitlab.com/isard/isardvdi/sessions/sessions"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func NewSessionsServer(log *zerolog.Logger, wg *sync.WaitGroup, addr string, sessions sessions.Interface) *SessionsServer {
	return &SessionsServer{
		sessions: sessions,
		addr:     addr,

		log: log,
		wg:  wg,
	}
}

// TODO: Test the sessions package

type SessionsServer struct {
	sessions sessions.Interface
	addr     string

	log *zerolog.Logger
	wg  *sync.WaitGroup

	sessionsv1.UnimplementedSessionsServiceServer
}

func (s *SessionsServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, s.log, s.wg, func(srv *gRPC.Server) {
		sessionsv1.RegisterSessionsServiceServer(srv, s)
	}, s.addr)
}

func (s *SessionsServer) New(ctx context.Context, req *sessionsv1.NewRequest) (*sessionsv1.NewResponse, error) {
	sess, err := s.sessions.New(ctx, req.GetUserId(), req.GetRemoteAddr())
	if err != nil {
		if errors.Is(err, sessions.ErrMissingUserID) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		if errors.Is(err, sessions.ErrInvalidRemoteAddr) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("create new session: %w", err).Error())
	}

	return &sessionsv1.NewResponse{
		Id: sess.ID,
		Time: &sessionsv1.NewResponseTime{
			MaxTime:        timestamppb.New(sess.Time.MaxTime),
			MaxRenewTime:   timestamppb.New(sess.Time.MaxRenewTime),
			ExpirationTime: timestamppb.New(sess.Time.ExpirationTime),
		},
	}, nil
}

func (s *SessionsServer) Get(ctx context.Context, req *sessionsv1.GetRequest) (*sessionsv1.GetResponse, error) {
	sess, err := s.sessions.Get(ctx, req.GetId(), req.GetRemoteAddr())
	if err != nil {
		if errors.Is(err, sessions.ErrInvalidRemoteAddr) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		if errors.Is(err, redis.ErrNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}

		if errors.Is(err, sessions.ErrRemoteAddrMismatch) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		if errors.Is(err, sessions.ErrSessionExpired) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("get session: %w", err).Error())
	}

	return &sessionsv1.GetResponse{
		Time: &sessionsv1.GetResponseTime{
			MaxTime:        timestamppb.New(sess.Time.MaxTime),
			MaxRenewTime:   timestamppb.New(sess.Time.MaxRenewTime),
			ExpirationTime: timestamppb.New(sess.Time.ExpirationTime),
		},
	}, nil
}

func (s *SessionsServer) GetUserSession(ctx context.Context, req *sessionsv1.GetUserSessionRequest) (*sessionsv1.GetUserSessionResponse, error) {
	sess, err := s.sessions.GetUserSession(ctx, req.GetUserId())
	if err != nil {
		if errors.Is(err, sessions.ErrMissingUserID) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		if errors.Is(err, redis.ErrNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("get user session: %w", err).Error())
	}

	return &sessionsv1.GetUserSessionResponse{
		Id: sess.ID,
		Time: &sessionsv1.GetUserSessionResponseTime{
			MaxTime:        timestamppb.New(sess.Time.MaxTime),
			MaxRenewTime:   timestamppb.New(sess.Time.MaxRenewTime),
			ExpirationTime: timestamppb.New(sess.Time.ExpirationTime),
		},
	}, nil
}

func (s *SessionsServer) Renew(ctx context.Context, req *sessionsv1.RenewRequest) (*sessionsv1.RenewResponse, error) {
	sess, err := s.sessions.Renew(ctx, req.GetId(), req.GetRemoteAddr())
	if err != nil {
		if errors.Is(err, sessions.ErrInvalidRemoteAddr) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		if errors.Is(err, redis.ErrNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}

		if errors.Is(err, sessions.ErrRemoteAddrMismatch) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		if errors.Is(err, sessions.ErrRenewTimeExpired) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		if errors.Is(err, sessions.ErrMaxSessionTime) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("renew session: %w", err).Error())
	}

	return &sessionsv1.RenewResponse{
		Time: &sessionsv1.RenewResponseTime{
			MaxTime:        timestamppb.New(sess.MaxTime),
			MaxRenewTime:   timestamppb.New(sess.MaxRenewTime),
			ExpirationTime: timestamppb.New(sess.ExpirationTime),
		},
	}, nil
}

func (s *SessionsServer) Revoke(ctx context.Context, req *sessionsv1.RevokeRequest) (*sessionsv1.RevokeResponse, error) {
	if err := s.sessions.Revoke(ctx, req.GetId()); err != nil {
		if errors.Is(err, redis.ErrNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("revoke session: %w", err).Error())
	}

	return &sessionsv1.RevokeResponse{}, nil
}
