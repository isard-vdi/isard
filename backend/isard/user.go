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

	if err := i.UserDesktops(u); err != nil {
		return err
	}

	return nil
}

func (i *Isard) UserUpdate(u *model.User) error {
	if u.Name == "" || u.Email == "" {
		return nil
	}
	params := url.Values{
		"name": {u.Name},
		"email": {u.Email},
	}
	if u.Photo != "" {
		params.Add("photo", u.Photo)
	}
	req, err := http.NewRequest(http.MethodPut, i.url("user/"+u.ID()), strings.NewReader(params.Encode()))
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

type userDesktopRsp struct {
	ID   string `json:"id,omitempty"`
	Name string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
	State string `json:"state,omitempty"`
	Type string `json:"type,omitempty"`
	Template string `json:"template,omitempty"`
	Viewers []string `json:"viewers,omitempty"`
	Icon string `json:"icon,omitempty"`
	Image string `json:"image,omitempty"`
}

func (i *Isard) UserDesktops(u *model.User) error {
	rsp, err := http.Get(i.url("user/" + u.ID() + "/desktops"))
	if err != nil {
		i.sugar.Errorw("get user desktops",
			"err", err,
			"id", u.ID(),
		)
		return fmt.Errorf("get user desktops: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get user desktops",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"id", u.ID(),
		)

		return fmt.Errorf("get user desktops: %w", err)
	}

	desktops := []userDesktopRsp{}
	if err := json.NewDecoder(rsp.Body).Decode(&desktops); err != nil {
		i.sugar.Errorw("get user desktops: decode JSON response",
			"err", err,
		)

		return fmt.Errorf("get user desktops: decode JSON response: %w", err)
	}

	for _, t := range desktops {
		u.Desktops = append(u.Desktops, model.Desktop{
			ID:   t.ID,
			Name: t.Name,
			Description: t.Description,
			State: t.State,
			Type: t.Type,
			Template: t.Template,
			Viewers: t.Viewers,
			Icon: t.Icon,
			Image: t.Image,
		})
	}

	return nil
}

type userTemplateRsp struct {
	ID   string `json:"id,omitempty"`
	Name string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
	Icon string `json:"icon,omitempty"`
	Image string `json:"image,omitempty"`
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
			Description: t.Description,
			Icon: t.Icon,
			Image: t.Image,
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
