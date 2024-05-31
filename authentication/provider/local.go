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

func (l *Local) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *model.User, string, *ProviderError) {
	usr := *args.FormUsername
	pwd := *args.FormPassword

	u := &model.User{
		UID:      usr,
		Username: usr,
		Provider: types.Local,
		Category: categoryID,
	}
	if err := u.LoadWithoutID(ctx, l.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			return nil, nil, "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("user not found"),
			}
		}

		return nil, nil, "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("load user from DB: %w", err),
		}
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(pwd)); err != nil {
		return nil, nil, "", &ProviderError{
			User:   ErrInvalidCredentials,
			Detail: errors.New("invalid password"),
		}
	}

	return nil, u, "", nil
}

func (l *Local) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, *model.User, string, *ProviderError) {
	return nil, nil, "", &ProviderError{
		User:   errInvalidIDP,
		Detail: errors.New("the local provider doesn't support the callback operation"),
	}
}

func (Local) AutoRegister() bool {
	return false
}

func (l *Local) String() string {
	return types.Local
}

func (l *Local) Healthcheck() error {
	rsp, err := r.Table("users").Status().Run(l.db)
	if err != nil {
		return fmt.Errorf("unable to connect to the DB: %w", err)
	}

	defer rsp.Close()

	var res []interface{}
	if rsp.All(&res); err != nil {
		return fmt.Errorf("unable to connect to the DB: read DB response: %w", err)
	}

	return nil
}
