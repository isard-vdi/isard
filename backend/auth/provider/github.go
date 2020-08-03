package provider

import (
	"encoding/gob"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strconv"

	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/github"
)

func init() {
	gob.Register(&GitHub{})
}

const provGitHub = "github"

// GitHub implements the service provider for github.com
type GitHub struct{}

func (GitHub) String() string {
	return provGitHub
}

func (GitHub) cfg(env *env.Env) *oauth2.Config {
	return &oauth2.Config{
		ClientID:     env.Cfg.Auth.GitHub.ID,
		ClientSecret: env.Cfg.Auth.GitHub.Secret,
		Scopes:       []string{},
		Endpoint:     github.Endpoint,
	}
}

func (g GitHub) Login(env *env.Env, w http.ResponseWriter, r *http.Request) {
	oauth2Login(env, g, w, r)
}

func (g GitHub) Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	oauth2Callback(env, w, r)
}

func (g GitHub) NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{}) {
	oauth2NewSession(env, w, r, g, u, val)
}

// TOOD: Groups / Organizations and stuff
func (g GitHub) Get(env *env.Env, u *model.User, val interface{}) error {
	url := url.URL{
		Scheme: "https",
		Host:   env.Cfg.Auth.GitHub.Host,
		Path:   "/user",
	}

	req, err := http.NewRequest(http.MethodGet, url.String(), http.NoBody)
	if err != nil {
		return fmt.Errorf("build HTTP request: %w", err)
	}
	req.Header.Add("Authorization", "token "+val.(*oauth2.Token).AccessToken)
	req.Header.Add("Accept", "application/vnd.github.v3+json")

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("call GitHub API: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		// TODO: Handle token refresh
		b, _ := ioutil.ReadAll(rsp.Body)
		return fmt.Errorf("call GitHub API: http code: %d: %s", rsp.StatusCode, b)
	}

	apiUsr := &githubUsrJSON{}
	if err := json.NewDecoder(rsp.Body).Decode(&apiUsr); err != nil {
		return fmt.Errorf("unmarshal JSON response: %w", err)
	}

	u.UID = strconv.Itoa(apiUsr.UID)
	u.Username = apiUsr.Username
	u.Provider = g.String()
	u.Name = apiUsr.Name
	u.Email = apiUsr.Email
	u.Photo = apiUsr.Photo

	return nil
}

type githubUsrJSON struct {
	UID      int    `json:"id,omitempty"`
	Username string `json:"login,omitempty"`
	Name     string `json:"name,omitempty"`
	Email    string `json:"email,omitempty"`
	Photo    string `json:"avatar_url,omitempty"`
}
