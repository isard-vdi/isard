package provider

import (
	"encoding/gob"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strings"

	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
)

func init() {
	gob.Register(&Google{})
}

const provGoogle = "google"

type Google struct{}

func (Google) String() string {
	return provGoogle
}

func (Google) cfg(env *env.Env) *oauth2.Config {
	return &oauth2.Config{
		ClientID:     env.Cfg.Auth.Google.ID,
		ClientSecret: env.Cfg.Auth.Google.Secret,
		Scopes: []string{
			"https://www.googleapis.com/auth/userinfo.email",
			"https://www.googleapis.com/auth/userinfo.profile",
		},
		Endpoint:    google.Endpoint,
		RedirectURL: fmt.Sprintf("https://%s/callback/google", env.Cfg.BackendHost),
	}
}

func (g Google) Login(env *env.Env, w http.ResponseWriter, r *http.Request) {
	oauth2Login(env, g, w, r)
}

func (Google) Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	oauth2Callback(env, w, r)
}

func (g Google) NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{}) {
	oauth2NewSession(env, w, r, g, u, val)
}

func (g Google) Get(env *env.Env, u *model.User, val interface{}) error {
	q := url.Values{"access_token": {val.(*oauth2.Token).AccessToken}}
	url := url.URL{
		Scheme:   "https",
		Host:     "www.googleapis.com",
		Path:     "oauth2/v2/userinfo",
		RawQuery: q.Encode(),
	}

	rsp, err := http.Get(url.String())
	if err != nil {
		return fmt.Errorf("call Google API: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		// TODO: Handle token refresh
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		env.Sugar.Errorw("call Google API",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
		)

		return fmt.Errorf("oauth2: %w", err)
	}

	apiUsr := &googleUsrJSON{}
	if err := json.NewDecoder(rsp.Body).Decode(&apiUsr); err != nil {
		return fmt.Errorf("unmarshal json response: %w", err)
	}

	u.UID = apiUsr.UID
	u.Username = strings.Split(apiUsr.Email, "@")[0]
	u.Provider = g.String()
	u.Name = apiUsr.Name
	u.Email = apiUsr.Email
	u.Photo = apiUsr.Photo

	return nil
}

type googleUsrJSON struct {
	UID   string `json:"id,omitempty"`
	Name  string `json:"name,omitempty"`
	Email string `json:"email,omitempty"`
	Photo string `json:"picture,omitempty"`
}
