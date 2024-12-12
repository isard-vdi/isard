package authentication

import (
	"context"

	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) MigrateUser(ctx context.Context, tkn string, userID string) (string, error) {
	if err := token.TokenIsIsardvdiService(a.Secret, tkn); err != nil {
		return "", err
	}

	migrationTkn, err := token.SignUserMigrationToken(a.Secret, userID)
	if err != nil {
		return "", err
	}

	a.Log.Info().Str("user_id", userID).Str("tkn", migrationTkn).Msg("migrate user")

	return migrationTkn, nil
}
