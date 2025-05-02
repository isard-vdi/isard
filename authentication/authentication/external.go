package authentication

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) ExternalUser(ctx context.Context, tkn string, UserID string, role string, username string, name string, email string, photo string) (string, error) {
	// Firstly check if the external app token is valid
	claims, err := token.ParseExternalToken(a.DB, tkn)
	if err != nil {
		return "", err
	}

	// Check if the app is allowed to create users
	if model.Role(claims.Role).HasLessPrivileges(model.RoleManager) {
		return "", errors.New("external app with role less than manager cannot create users")
	}
	// Check if the user that wants to create the user is allowed to do so
	if !model.Role(role).HasEqualOrLessPrivileges(model.Role(claims.Role)) {
		return "", errors.New("external app cannot create users with role greater than manager")
	}

	g := &model.Group{
		Category:      claims.CategoryID,
		ExternalAppID: claims.KeyID,
		ExternalGID:   fmt.Sprintf("%s_%s", types.ProviderExternal, claims.KeyID),
	}

	// Check if the group exists
	exists, err := g.Exists(ctx, a.DB)
	if err != nil {
		return "", err
	}

	if !exists {
		// We can safely set this parameters, since they're not going to be overrided if the group exists
		g.Description = "This is a auto register created by the authentication service. This group maps a group of an external app"
		// Get the provider external
		g.GenerateNameExternal(types.ProviderExternal)
		err = a.registerGroup(g)
		if err != nil {
			return "", err
		}
		// Reload the group from the db to get the ID
		err = g.LoadExternal(ctx, a.DB)
		if err != nil {
			return "", err
		}
	}

	// Then create the user data
	u := &model.User{
		Provider: fmt.Sprintf("%s_%s", types.ProviderExternal, claims.KeyID),
		Category: claims.CategoryID,
		Group:    g.ID,

		UID: UserID,

		Role:     model.Role(role),
		Username: username,
		Name:     name,
		Email:    email,
		Photo:    photo,
	}

	err = a.registerUser(u)
	if err != nil {
		return "", err
	}

	// Reload the user from the db to get the ID
	err = u.Load(ctx, a.DB)
	if err != nil {
		return "", err
	}

	a.Log.Info().Str("user_id", u.ID).Str("user_id", u.ID).Msg("external user")

	return u.ID, nil
}
