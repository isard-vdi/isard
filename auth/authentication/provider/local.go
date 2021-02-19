package provider

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/auth/authentication/store"
	"gitlab.com/isard/isardvdi/pkg/model"

	"github.com/go-pg/pg/v10"
	"github.com/gorilla/sessions"
	"golang.org/x/crypto/bcrypt"
)

const provLocal = "local"

type Local struct {
	Store sessions.Store
	DB    *pg.DB
}

func (Local) String() string {
	return provLocal
}

type localLoginArgs struct {
	Usr string
	Pwd string
}

func parseLocalLoginArgs(args map[string]interface{}) (*localLoginArgs, bool) {
	u, ok := args["usr"]
	if !ok {
		return nil, false
	}

	usr, ok := u.(string)
	if !ok {
		return nil, false
	}

	p, ok := args["pwd"]
	if !ok {
		return nil, false
	}

	pwd, ok := p.(string)
	if !ok {
		return nil, false
	}

	return &localLoginArgs{
		Usr: usr,
		Pwd: pwd,
	}, true
}

func (l *Local) Login(ctx context.Context, entityID string, args map[string]interface{}) (string, string, error) {
	a, ok := parseLocalLoginArgs(args)
	if !ok {
		return "", "", errors.New("invalid arguments")
	}

	u := &model.User{Username: a.Usr}
	if err := u.LoadWithUsername(ctx, l.DB, entityID); err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return "", "", ErrInvalidCredentials
		}

		return "", "", fmt.Errorf("load DB user: %w", err)
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(a.Pwd)); err != nil {
		return "", "", ErrInvalidCredentials
	}

	r := store.BuildHTTPRequest(ctx, "")

	s, err := l.Store.New(r, store.SessionStoreKey)
	if err != nil {
		return "", "", fmt.Errorf("create session: %w", err)
	}

	val := store.NewStoreValues(nil)
	val.SetProvider(l.String())
	val.SetUsrID(u.UUID)
	val.SetTime(time.Now())

	s.Values = val.Values()

	w := store.BuildHTTPResponseWriter()
	if err := s.Save(r, w); err != nil {
		return "", "", fmt.Errorf("save session: %w", err)
	}

	token, err := store.GetToken(w)
	if err != nil {
		return "", "", fmt.Errorf("get token: %w", err)
	}

	return token, "", nil
}

func (l *Local) Logout(ctx context.Context, s *sessions.Session) (string, error) {
	s.Options.MaxAge = -1

	r := store.BuildHTTPRequest(ctx, "")
	w := store.BuildHTTPResponseWriter()

	return "", s.Save(r, w)
}

func (l *Local) Get(ctx context.Context, u *model.User) error {
	return u.LoadWithUUID(ctx, l.DB)
}
