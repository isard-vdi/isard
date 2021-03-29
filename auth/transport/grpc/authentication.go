package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/auth/authentication/provider"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (a *AuthServer) Login(ctx context.Context, req *auth.LoginRequest) (*auth.LoginResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"provider":   &req.Provider,
		"entityUUID": &req.EntityUuid,
	}); err != nil {
		return nil, err
	}

	u, token, redirect, err := a.Authentication.Login(ctx, req.Provider, req.EntityUuid, map[string]interface{}{
		"usr": req.Usr,
		"pwd": req.Pwd,
	})
	if err != nil {
		panic(err)
	}

	return &auth.LoginResponse{
		Redirect: redirect,
		Token:    token,
		Uuid:     u.UUID,
		Name:     u.Name,
		Surname:  u.Surname,
	}, nil
}

func (a *AuthServer) GetUserID(ctx context.Context, req *auth.GetUserIDRequest) (*auth.GetUserIDResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"token": &req.Token,
	}); err != nil {
		return nil, err
	}

	usr, entity, err := a.Authentication.Get(ctx, req.Token)
	if err != nil {
		if errors.Is(err, provider.ErrNotAuthenticated) {
			return nil, status.Error(codes.Unauthenticated, err.Error())
		}

		return nil, status.Error(codes.Unknown, err.Error())
	}

	return &auth.GetUserIDResponse{
		Id:       int64(usr),
		EntityId: int64(entity),
	}, nil
}
