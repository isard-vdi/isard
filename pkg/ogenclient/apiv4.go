package ogenclient

import (
	"context"
	"errors"
	"fmt"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
)

// ErrMissingToken is returned by APIv4Context when the context carries no token.
var ErrMissingToken = errors.New("no apiv4 token in the context")

// APIv4Source signs a fresh admin JWT per request using the shared service secret.
// Use this for service-to-service apiv4 clients (orchestrator, authentication, stats).
type APIv4Source struct {
	Secret string
}

func (s APIv4Source) HTTPBearer(_ context.Context, _ string) (apiv4.HTTPBearer, error) {
	tkn, err := SignServiceJWT(s.Secret)
	if err != nil {
		return apiv4.HTTPBearer{}, fmt.Errorf("sign apiv4 jwt: %w", err)
	}
	return apiv4.HTTPBearer{Token: tkn}, nil
}

// APIv4Static adapts a pre-issued bearer token to apiv4.SecuritySource.
// Use for clients constructed after a separate login flow (check).
type APIv4Static struct {
	Token string
}

func (s APIv4Static) HTTPBearer(_ context.Context, _ string) (apiv4.HTTPBearer, error) {
	return apiv4.HTTPBearer{Token: s.Token}, nil
}

type apiv4TokenCtxKeyType string

const apiv4TokenCtxKey apiv4TokenCtxKeyType = "apiv4_token"

// ContextWithAPIv4Token returns a copy of ctx carrying the bearer token
// APIv4Context authenticates with.
func ContextWithAPIv4Token(ctx context.Context, tkn string) context.Context {
	return context.WithValue(ctx, apiv4TokenCtxKey, tkn)
}

// APIv4Context reads the bearer token from each request's context, so one
// long-lived client can serve requests authenticated as different users.
// Use it wherever the token changes per request, since a client per token
// is a connection pool per token.
type APIv4Context struct{}

// HTTPBearer returns the token ContextWithAPIv4Token put in ctx, or ErrMissingToken.
func (s APIv4Context) HTTPBearer(ctx context.Context, _ string) (apiv4.HTTPBearer, error) {
	tkn, ok := ctx.Value(apiv4TokenCtxKey).(string)
	if !ok {
		return apiv4.HTTPBearer{}, ErrMissingToken
	}

	return apiv4.HTTPBearer{Token: tkn}, nil
}
