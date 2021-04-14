package isard

import (
	"fmt"
	"io/ioutil"
	"net/http"

	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

func (i *Isard) Vpn(u *model.User) ([]byte, error) {
	rsp, err := http.Get(i.url(fmt.Sprintf("user/%s/vpn/config", u.ID())))
	if err != nil {
		i.sugar.Errorw("get vpn",
			"err", err,
		)
		return nil, fmt.Errorf("get viewer: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get vpn",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
		)

		return nil, fmt.Errorf("get vpn: %w", err)
	}

	return ioutil.ReadAll(rsp.Body)
}
