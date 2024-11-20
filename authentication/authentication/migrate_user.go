package authentication

import (
	"context"

	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) MigrateUser(ctx context.Context, tkn string) (string, error) {
	claims, err := token.ParseLoginToken(a.Secret, tkn)
	if err != nil {
		return "", err
	}

	// TODO: Check if the user is eligible for a user migration

	migrationTkn, err := token.SignUserMigrationToken(a.Secret, claims.Data.ID)
	if err != nil {
		return "", err
	}

	a.Log.Info().Str("user_id", claims.Data.ID).Msg("migrate user")

	return migrationTkn, nil
}
