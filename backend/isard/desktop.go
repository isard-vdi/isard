package isard

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strconv"

	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

func (i *Isard) DesktopCreate(u *model.User, tmpl string, persistent bool) (string, error) {
	rsp, err := http.PostForm(i.url("desktop"), url.Values{
		"id":         {u.ID()},
		"template":   {tmpl},
		"persistent": {strconv.FormatBool(persistent)},
	})
	if err != nil {
		i.sugar.Errorw("desktop create",
			"err", err,
			"usr", u.ID(),
			"tmpl", tmpl,
			"persistent", persistent,
		)

		return "", fmt.Errorf("desktop create: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("desktop create",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"usr", u.ID(),
			"tmpl", tmpl,
			"persistent", persistent,
		)

		return "", fmt.Errorf("desktop create: %w", err)
	}

	d := &desktopCreateRsp{}
	if err := json.NewDecoder(rsp.Body).Decode(d); err != nil {
		i.sugar.Errorw("desktop create: unmarshal JSON response",
			"err", err,
			"usr", u.ID(),
			"tmpl", tmpl,
			"persistent", persistent,
		)

		return "", fmt.Errorf("desktop create: %w", err)
	}

	return d.ID, nil
}

func (i *Isard) DesktopDelete(id string) error {
	req, err := http.NewRequest(http.MethodDelete, i.url("desktop/"+id), http.NoBody)
	if err != nil {
		i.sugar.Errorw("delete desktop: create http request",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("delete desktop: create http request: %w", err)
	}

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		i.sugar.Errorw("delete desktop",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("delete desktop: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("delete desktop",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", id,
		)

		return fmt.Errorf("delete desktop: %w", err)
	}

	return nil
}

func (i *Isard) DesktopStart(id string) error {
	req, err := http.NewRequest(http.MethodGet, i.url("desktop/start/"+id), http.NoBody)
	if err != nil {
		i.sugar.Errorw("start desktop: start http request",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("start desktop: start http request: %w", err)
	}

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		i.sugar.Errorw("start desktop",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("start desktop: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("start desktop",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", id,
		)

		return fmt.Errorf("start desktop: %w", err)
	}

	return nil
}

func (i *Isard) DesktopStop(id string) error {
	req, err := http.NewRequest(http.MethodGet, i.url("desktop/stop/"+id), http.NoBody)
	if err != nil {
		i.sugar.Errorw("stop desktop: stop http request",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("stop desktop: stop http request: %w", err)
	}

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		i.sugar.Errorw("stop desktop",
			"err", err,
			"id", id,
		)

		return fmt.Errorf("stop desktop: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("stop desktop",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", id,
		)

		return fmt.Errorf("stop desktop: %w", err)
	}

	return nil
}

type desktopCreateRsp struct {
	ID string `json:"id,omitempty"`
}
