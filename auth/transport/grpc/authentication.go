package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
)

func (a *AuthServer) Login(ctx context.Context, req *auth.LoginRequest) (*auth.LoginResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"provider": &req.Provider,
		"entityID": &req.EntityId,
	}); err != nil {
		return nil, err
	}

	token, redirect, err := a.Authentication.Login(ctx, req.Provider, req.EntityId, map[string]interface{}{
		"usr": req.Usr,
		"pwd": req.Pwd,
	})
	if err != nil {
		panic(err)
	}

	return &auth.LoginResponse{
		Token:    token,
		Redirect: redirect,
	}, nil
}
