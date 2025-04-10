package authentication

import (
	"context"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) GenerateAPIKey(ctx context.Context, tkn string, expirationMinutes int) (string, error) {
	parsedTkn, err := token.ParseLoginToken(a.Secret, tkn)
	if err != nil {
		return "", err
	}

	// Retrieve the user from the token
	user := &model.User{
		ID: parsedTkn.Data.ID,
	}
	err = user.Load(ctx, a.DB)
	if err != nil {
		return "", err
	}

	// Check that the role must be at least advanced
	model.Role(user.Role).HasEqualOrMorePrivileges(model.RoleAdvanced)
	if err != nil {
		return "", err
	}

	usrExternalTkn, err := token.SignApiKey(a.Secret, user, expirationMinutes)
	if err != nil {
		return "", err
	}

	// Set the API key to the one that has been generated and update the user
	user.ApiKey = usrExternalTkn
	err = user.Update(ctx, a.DB)
	if err != nil {
		return "", err
	}

	a.Log.Info().Str("user_id", parsedTkn.Data.ID).Str("tkn", usrExternalTkn).Msg("external user")

	return usrExternalTkn, nil
}
