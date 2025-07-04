package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"

	"golang.org/x/crypto/bcrypt"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &Local{}

type Local struct {
	db r.QueryExecutor
}

func InitLocal(db r.QueryExecutor) *Local {
	return &Local{db}
}

func (l *Local) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	usr := *args.FormUsername
	pwd := *args.FormPassword

	data := &types.ProviderUserData{
		Provider: types.ProviderLocal,
		Category: categoryID,
		UID:      usr,

		Username: &usr,
	}

	u := data.ToUser()

	if err := u.LoadWithoutID(ctx, l.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("user not found"),
			}
		}

		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("load user from DB: %w", err),
		}
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(pwd)); err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInvalidCredentials,
			Detail: errors.New("invalid password"),
		}
	}

	// Update data with the new user information,
	// as it may have data that is unknown in this point
	data.FromUser(u)

	return nil, []*model.Group{}, data, "", "", nil
}

func (l *Local) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, nil, "", "", &ProviderError{
		User:   errInvalidIDP,
		Detail: errors.New("the local provider doesn't support the callback operation"),
	}
}

func (Local) AutoRegister(*model.User) bool {
	return false
}

func (l *Local) String() string {
	return types.ProviderLocal
}

func (l *Local) Healthcheck() error {
	rsp, err := r.Table("users").Status().Run(l.db)
	if err != nil {
		return fmt.Errorf("unable to connect to the DB: %w", err)
	}

	defer rsp.Close()

	var res []interface{}
	if err := rsp.All(&res); err != nil {
		return fmt.Errorf("unable to connect to the DB: read DB response: %w", err)
	}

	return nil
}

func (Local) Logout(context.Context, string) (string, error) {
	return "", nil
}
