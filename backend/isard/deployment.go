package isard

import (
	"fmt"
	"io/ioutil"
	"net/http"

	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

func (i *Isard) DeploymentGet(u *model.User, id string) ([]byte, error) {
	req, err := http.NewRequest(http.MethodGet, i.url(fmt.Sprintf("user/%s/deployment/%s", u.ID(), id)), http.NoBody)
	if err != nil {
		i.sugar.Errorw("get deployment: start http request",
			"err", err,
			"id", id,
		)

		return nil, fmt.Errorf("get deployment: start http request: %w", err)
	}

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		i.sugar.Errorw("get deployment",
			"err", err,
			"id", id,
		)

		return nil, fmt.Errorf("get deployment: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get deployment",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", id,
		)

		return nil, fmt.Errorf("get deployment: %w", err)
	}

	return ioutil.ReadAll(rsp.Body)
}
