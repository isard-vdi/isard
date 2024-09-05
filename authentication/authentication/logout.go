package authentication

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/token"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (a *Authentication) Logout(ctx context.Context, tkn string) error {
	claims, err := token.ParseLoginToken(a.Secret, tkn)
	if err != nil {
		return fmt.Errorf("parse the login token: %w", err)
	}

	if _, err := a.Sessions.Revoke(ctx, &sessionsv1.RevokeRequest{
		Id: claims.SessionID,
	}); err != nil {
		status, ok := status.FromError(err)

		// If the status code is not found, we ignore the error, to ensure the user
		// that the session is 100% closed. Otherwise return the error
		if !ok || status.Code() != codes.NotFound {
			return fmt.Errorf("revoke session: %w", err)
		}
	}

	return nil
}
