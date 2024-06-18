package authentication

import (
	"context"
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
)

func (a *Authentication) Renew(ctx context.Context, ss, remoteAddr string) (string, error) {
	claims, err := token.ParseLoginToken(a.Secret, ss)
	if err != nil {
		// When the token is expired, it might be able to be renewed
		if !errors.Is(err, jwt.ErrTokenExpired) {
			return "", err
		}
	}

	renew, err := a.Sessions.Renew(ctx, &sessionsv1.RenewRequest{
		Id:         claims.SessionID,
		RemoteAddr: remoteAddr,
	})
	if err != nil {
		return "", fmt.Errorf("renew token: %w", err)
	}

	u := &model.User{
		Provider: claims.Data.Provider,
		ID:       claims.Data.ID,
		Role:     model.Role(claims.Data.RoleID),
		Category: claims.Data.CategoryID,
		Group:    claims.Data.GroupID,
		Name:     claims.Data.Name,
	}

	tkn, err := token.SignLoginToken(a.Secret, renew.Time.ExpirationTime.AsTime(), claims.SessionID, u)
	if err != nil {
		return "", fmt.Errorf("sign the login token: %w", err)
	}

	return tkn, nil
}
