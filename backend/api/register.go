package api

import (
	"bytes"
	"encoding/base64"
	"encoding/gob"
	"errors"
	"fmt"
	"net/http"

	"github.com/isard-vdi/isard/backend/auth/provider"
)

func (a *API) register(w http.ResponseWriter, r *http.Request) {
	c, err := r.Cookie(provider.AutoRegistrationCookieKey)
	if err != nil {
		handleErr(errors.New("no registration cookie found. Login first"), w, r)
		return
	}

	b, err := base64.StdEncoding.DecodeString(c.Value)
	if err != nil {
		a.env.Sugar.Errorw("decode autoregistration cookie: base64",
			"err", err,
		)

		handleErr(fmt.Errorf("decode autoregistration cookie: base64: %w", err), w, r)
		return
	}

	autoRegistrationCookie := &provider.AutoRegistrationCookieStruct{}
	if err := gob.NewDecoder(bytes.NewBuffer(b)).Decode(autoRegistrationCookie); err != nil {
		a.env.Sugar.Errorw("decode autoregistration cookie: gob",
			"err", err,
		)

		handleErr(fmt.Errorf("decode autoregistration cookie: gob: %w", err), w, r)
		return
	}

	autoRegistrationCookie.Provider.NewSession(a.env, w, r, autoRegistrationCookie.User, autoRegistrationCookie.Val)
}
