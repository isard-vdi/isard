package http

import (
	"context"

	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"
)

type tokenCtxKeyType string

const tokenCtxKey tokenCtxKeyType = "token"

type SecurityHandler struct{}

func (SecurityHandler) HandleBearerAuth(ctx context.Context, operationName string, t oasAuthentication.BearerAuth) (context.Context, error) {
	return context.WithValue(ctx, tokenCtxKey, t.Token), nil
}
