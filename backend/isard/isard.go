package isard

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"path"

	"github.com/isard-vdi/isard/backend/pkg/utils"
	"github.com/isard-vdi/isard/backend/model"
	"go.uber.org/zap"
)

// ErrUnknownViewerType is an unknown viewer
var ErrUnknownViewerType = errors.New("unknown viewer type")

const apiEndpoint = "/api/v2"

// Isard is the Isard API client
type Isard struct {
	sugar *zap.SugaredLogger
	host  string
	port  int
}

// New initializes the Isard client
func New(sugar *zap.SugaredLogger, host string, port int) *Isard {
	return &Isard{sugar, host, port}
}

func (i *Isard) url(endpoint string) string {
	u := &url.URL{
		Scheme: "http",
		Host:   fmt.Sprintf("%s:%d", i.host, i.port),
		Path:   path.Join(apiEndpoint, endpoint),
	}

	return u.String()
}

type loginRsp struct {
	ID      string `json:"id,omitempty"`
	Success bool `json:"success,omitempty"`
}

func (i *Isard) Login(usr *model.User, pwd string) error {
	rsp, err := http.PostForm(i.url("login"), url.Values{
		"id":     {usr.ID()},
		"passwd": {pwd},
	})
	if err != nil {
		i.sugar.Errorw("login",
			"err", err,
			"usr", usr.ID(),
		)

		return fmt.Errorf("login: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		defer rsp.Body.Close()
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("login",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"usr", usr.ID(),
		)

		return fmt.Errorf("login: %w", err)
	}

	login := loginRsp{}
	if err := json.NewDecoder(rsp.Body).Decode(&login); err != nil {
		i.sugar.Errorw("login: decode JSON response",
			"err", err,
		)

		return fmt.Errorf("login: decode JSON response: %w", err)
	}
	usr.LoadFromID(login.ID)
	return nil
}
