package ogenclient

import (
	"context"
	"fmt"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
)

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
// Use for clients constructed after a separate login flow (check, websockify, rdpgw).
type APIv4Static struct {
	Token string
}

func (s APIv4Static) HTTPBearer(_ context.Context, _ string) (apiv4.HTTPBearer, error) {
	return apiv4.HTTPBearer{Token: s.Token}, nil
}
