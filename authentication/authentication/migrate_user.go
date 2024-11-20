package authentication

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) MigrateUser(ctx context.Context, tkn string) (string, error) {
	typ, err := token.GetTokenType(tkn)
	if err != nil {
		return "", fmt.Errorf("get the JWT token type: %w", err)
	}

	var userID string

	switch typ {
	// User is required to migrate themselves
	case token.TypeUserMigrationRequired:
		claims, err := token.ParseUserMigrationRequiredToken(a.Secret, tkn)
		if err != nil {
			return "", err
		}

		userID = claims.UserID

	// User has chosen to migrate themselves
	case token.TypeLogin:
		claims, err := token.ParseLoginToken(a.Secret, tkn)
		if err != nil {
			return "", err
		}

		userID = claims.Data.ID

	default:
		return "", token.ErrInvalidTokenType
	}

	// TODO: Check if the user is eligible for a user migration

	migrationTkn, err := token.SignUserMigrationToken(a.Secret, userID)
	if err != nil {
		return "", err
	}

	a.Log.Info().Str("user_id", userID).Msg("migrate user")

	return migrationTkn, nil
}
