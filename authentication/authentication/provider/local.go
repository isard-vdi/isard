package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"

	"gitlab.com/isard/isardvdi/authentication/model"

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

func (l *Local) Login(ctx context.Context, categoryID string, args map[string]string) (*model.User, string, error) {
	usr, pwd, err := parseLocalArgs(args)
	if err != nil {
		return nil, "", err
	}

	u := &model.User{
		UID:      usr,
		Username: usr,
		Provider: LocalString,
		Category: categoryID,
	}
	if err := u.Load(ctx, l.db); err != nil {
		if !errors.Is(err, model.ErrNotFound) {
			return nil, "", fmt.Errorf("load user from DB: %w", err)
		}

		// Try LDAP login
		id, err := l.ldapLogin(usr, pwd)
		if err != nil {
			return nil, "", ErrInvalidCredentials
		}

		u := model.UserFromID(id)
		if err := u.Load(ctx, l.db); err != nil {
			return nil, "", fmt.Errorf("load user from DB: %w", err)
		}

		return u, args["redirect"], nil
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(pwd)); err != nil {
		return nil, "", ErrInvalidCredentials
	}

	return u, args["redirect"], nil
}

// TODO: This should be an independent provider
func (l *Local) ldapLogin(usr, pwd string) (string, error) {
	form := url.Values{}
	form.Set("id", usr)
	form.Set("passwd", pwd)

	rsp, err := http.PostForm("http://isard-api:5000/api/v3/login_ldap", form)
	if err != nil {
		return "", fmt.Errorf("make HTTP POST call: %w", err)
	}

	b, err := io.ReadAll(rsp.Body)
	if err != nil {
		return "", fmt.Errorf("read response body: %w", err)
	}
	defer rsp.Body.Close()

	if rsp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP status code %d: %s", rsp.StatusCode, b)
	}

	j := map[string]string{}
	if err := json.Unmarshal(b, &j); err != nil {
		return "", fmt.Errorf("parse JSON response: %w", err)
	}

	return j["id"], nil
}

func (l *Local) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", errInvalidIDP
}

func (l *Local) String() string {
	return LocalString
}
