package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &External{}

type External struct {
	db r.QueryExecutor
}

func externalCheckRequiredArgs(args LoginArgs) error {
	if args.Token == nil {
		return errors.New("token not provided")
	}

	return nil
}

func (e *External) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	if err := externalCheckRequiredArgs(args); err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	claims, err := token.ParseExternalToken(e.db, *args.Token)
	if err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   err,
			Detail: errors.New("parse the external token"),
		}
	}

	if model.Role(claims.Role).HasEqualOrMorePrivileges(model.RoleAdmin) {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: errors.New("cannot create an admin user through an external app"),
		}
	}

	g := &model.Group{
		Category:      claims.CategoryID,
		ExternalAppID: claims.KeyID,
		ExternalGID:   claims.GroupID,
	}

	// We can safely set this parameters, since they're not going to be overrided if the group exists
	g.Description = "This is a auto register created by the authentication service. This group maps a group of an external app"
	g.GenerateNameExternal(e.String())

	role := model.Role(claims.Role)

	u := &types.ProviderUserData{
		Provider: fmt.Sprintf("%s_%s", e.String(), claims.KeyID),
		Category: claims.CategoryID,
		UID:      claims.UserID,

		Role:     &role,
		Username: &claims.Username,
		Name:     &claims.Name,
		Email:    &claims.Email,
		Photo:    &claims.Photo,
	}

	return g, u, "", "", nil
}

func (External) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, "", "", &ProviderError{
		User:   errInvalidIDP,
		Detail: errors.New("the external provider doesn't support the callback operation"),
	}
}

func (External) AutoRegister(*model.User) bool {
	return true
}

func (External) String() string {
	return types.ProviderExternal
}

func (External) Healthcheck() error {
	return nil
}
