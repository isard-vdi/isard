package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
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
