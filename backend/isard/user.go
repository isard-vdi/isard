package isard

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strings"

	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

func (i *Isard) UserLoad(u *model.User) error {
	rsp, err := http.Get(i.url("user/" + u.ID()))
	if err != nil {
		i.sugar.Errorw("get user",
			"err", err,
			"id", u.ID(),
		)
		return fmt.Errorf("get user: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		if rsp.StatusCode == http.StatusNotFound {
			return model.ErrNotFound
		}

		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get user",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
		)

		return fmt.Errorf("get user: %w", err)
	}

	if err := i.UserTemplates(u); err != nil {
		return err
	}

	return nil
}

func (i *Isard) UserUpdate(u *model.User) error {
	req, err := http.NewRequest(http.MethodPut, i.url("user/"+u.ID()), strings.NewReader(url.Values{
		"name":  {u.Name},
		"email": {u.Email},
		"photo": {u.Photo},
	}.Encode()))
	if err != nil {
		i.sugar.Errorw("update user: create request",
			"err", err,
			"id", u.ID(),
		)

		return fmt.Errorf("update user: create http request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		i.sugar.Errorw("update user",
			"err", err,
			"id", u.ID(),
		)
		return fmt.Errorf("update user: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("update user",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
		)

		return fmt.Errorf("update user: %w", err)
	}

	return nil
}

type userTemplateRsp struct {
	ID   string `json:"id,omitempty"`
	Name string `json:"name,omitempty"`
	Icon string `json:"icon,omitempty"`
}

func (i *Isard) UserTemplates(u *model.User) error {
	rsp, err := http.Get(i.url("user/" + u.ID() + "/templates"))
	if err != nil {
		i.sugar.Errorw("get user templates",
			"err", err,
			"id", u.ID(),
		)
		return fmt.Errorf("get user templates: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get user templates",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
		)

		return fmt.Errorf("get user templates: %w", err)
	}

	templates := []userTemplateRsp{}
	if err := json.NewDecoder(rsp.Body).Decode(&templates); err != nil {
		i.sugar.Errorw("get user templates: decode JSON response",
			"err", err,
		)

		return fmt.Errorf("get user templates: decode JSON response: %w", err)
	}

	for _, t := range templates {
		u.Templates = append(u.Templates, model.Template{
			ID:   t.ID,
			Name: t.Name,
			Icon: t.Icon,
		})
	}

	return nil
}

func (i *Isard) UserRegister(u *model.User) error {
	rsp, err := http.PostForm(i.url("user"), url.Values{
		"provider":      {u.Provider},
		"user_uid":      {u.UID},
		"user_username": {u.Username},
		"role":          {u.Role},
		"category":      {u.Category},
		"group":         {u.Group},
	})

	if err != nil {
		i.sugar.Errorw("register user",
			"err", err,
			"id", u.ID(),
			"role", u.Role,
			"category", u.Category,
			"group", u.Group,
		)

		return fmt.Errorf("register user: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("register user",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
			"role", u.Role,
			"category", u.Category,
			"group", u.Group,
		)

		return fmt.Errorf("register user: %w", err)
	}

	return nil
}
