package isard

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"

	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

type registerRsp struct {
	Role     string
	Category string
	Group    string
}

func (i *Isard) CheckRegistrationCode(u *model.User, code string) error {
	rsp, err := http.PostForm(i.url("register"), url.Values{"code": {code}})
	if err != nil {
		i.sugar.Errorw("check registration code",
			"err", err,
			"id", u.ID(),
			"code", code,
		)

		return fmt.Errorf("check registration code: %w", err)
	}

	if rsp.StatusCode != 200 {
		if rsp.StatusCode == http.StatusNotFound {
			return errors.New("invalid registration code")
		}

		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("check registration code",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
		)

		return fmt.Errorf("check registration code: %w", err)
	}

	props := &registerRsp{}
	if err := json.NewDecoder(rsp.Body).Decode(props); err != nil {
		i.sugar.Errorw("check registration code: decode JSON response",
			"err", err,
			"id", u.ID(),
		)

		return fmt.Errorf("check registration code: decode JSON response: %w", err)
	}

	u.Role = props.Role
	u.Category = props.Category
	u.Group = props.Group

	return nil
}
