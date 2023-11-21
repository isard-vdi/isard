package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"golang.org/x/crypto/bcrypt"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const LocalString = "local"

type Local struct {
	db r.QueryExecutor
}

func InitLocal(db r.QueryExecutor) *Local {
	return &Local{db}
}

type localArgs struct {
	Username string `json:"username,omitempty"`
	Password string `json:"password,omitempty"`
}

func parseLocalArgs(args map[string]string) (string, string, error) {
	username := args["username"]
	password := args["password"]

	creds := &localArgs{}
	if body, ok := args[RequestBodyArgsKey]; ok && body != "" {
		if err := json.Unmarshal([]byte(body), creds); err != nil {
			return "", "", fmt.Errorf("unmarshal local authentication request body: %w", err)
		}
	}

	if username == "" {
		if creds.Username == "" {
			return "", "", errors.New("username not provided")
		}

		username = creds.Username
	}

	if password == "" {
		if creds.Password == "" {
			return "", "", errors.New("password not provided")
		}

		password = creds.Password
	}

	return username, password, nil
}

func (l *Local) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	usr, pwd, err := parseLocalArgs(args)
	if err != nil {
		return nil, nil, "", err
	}

	u := &model.User{
		UID:      usr,
		Username: usr,
		Provider: LocalString,
		Category: categoryID,
	}
	if err := u.LoadWithoutID(ctx, l.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			return nil, nil, "", ErrInvalidCredentials
		}

		return nil, nil, "", fmt.Errorf("load user from DB: %w", err)
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(pwd)); err != nil {
		return nil, nil, "", ErrInvalidCredentials
	}

	return nil, u, "", nil
}

func (l *Local) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", errInvalidIDP
}

func (Local) AutoRegister() bool {
	return false
}

func (l *Local) String() string {
	return LocalString
}
