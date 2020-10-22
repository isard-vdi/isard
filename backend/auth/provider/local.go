package provider

import (
	"errors"
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/backend/model"

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

func (l *Local) Login(w http.ResponseWriter, r *http.Request) error {
	organization := r.FormValue("organization")
	usr := r.FormValue("usr")
	pwd := r.FormValue("pwd")

	u := &model.User{
		Organization: organization,
		Username:     usr,
	}
	if err := u.LoadWithUsername(r.Context(), l.DB); err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return ErrInvalidCredentials
		}

		return err
	}

	if err := bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(pwd)); err != nil {
		return ErrInvalidCredentials
	}

	s, err := l.Store.New(r, SessionStoreKey)
	if err != nil {
		return fmt.Errorf("create session: %w", err)
	}

	s.Values[ProviderStoreKey] = l.String()
	s.Values[UsrIDStoreKey] = u.ID

	if err := s.Save(r, w); err != nil {
		return fmt.Errorf("save session: %w", err)
	}

	return nil
}

func (l *Local) Get(u *model.User) error {
	return fmt.Errorf("not implemented yet")
}
