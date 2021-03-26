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

func (l *Local) Login(ctx context.Context, entityID string, args map[string]interface{}) (*model.User, string, string, error) {
	a, ok := parseLocalLoginArgs(args)
	if !ok {
		return nil, "", "", errors.New("invalid arguments")
	}

	u := &model.User{}
	idpUUID, err := u.LoadWithAuthLocal(ctx, l.DB, entityID, a.Usr)
	if err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return nil, "", "", ErrInvalidCredentials
		}

		return nil, "", "", fmt.Errorf("load DB user: %w", err)
	}

	cfg := model.GenerateAuthConfigLocal(u.AuthConfig[idpUUID]) // we can be sure that the value will exist, since it's returned from the DB directly

	if err := bcrypt.CompareHashAndPassword([]byte(cfg.Pwd), []byte(a.Pwd)); err != nil {
		return nil, "", "", ErrInvalidCredentials
	}

	r := store.BuildHTTPRequest(ctx, "")

	s, err := l.Store.New(r, store.SessionStoreKey)
	if err != nil {
		return nil, "", "", fmt.Errorf("create session: %w", err)
	}

	val := store.NewStoreValues(nil)
	val.SetProvider(l.String())
	val.SetUsrID(u.UUID)
	val.SetTime(time.Now())

	s.Values = val.Values()

	w := store.BuildHTTPResponseWriter()
	if err := s.Save(r, w); err != nil {
		return nil, "", "", fmt.Errorf("save session: %w", err)
	}

	token, err := store.GetToken(w)
	if err != nil {
		return nil, "", "", fmt.Errorf("get token: %w", err)
	}

	return u, token, "", nil
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
