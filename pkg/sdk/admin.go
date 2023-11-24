package isardvdi

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
)

type User struct {
	ID       *string `json:"id,omitempty"`
	Provider *string `json:"provider,omitempty"`
	Role     *string `json:"role,omitempty"`
	Category *string `json:"category,omitempty"`
	Group    *string `json:"group,omitempty"`
	UID      *string `json:"uid,omitempty"`
	Username *string `json:"username,omitempty"`
	Name     *string `json:"name,omitempty"`
}

func (c *Client) AdminUserList(ctx context.Context) ([]*User, error) {
	req, err := c.newRequest(http.MethodGet, "admin/users", nil)
	if err != nil {
		return nil, err
	}

	users := []*User{}
	if _, err := c.do(ctx, req, &users); err != nil {
		return nil, fmt.Errorf("user list: %w", err)
	}

	return users, nil
}

func (c *Client) AdminUserCreate(ctx context.Context, provider, role, category, group, uid, username, pwd string) (*User, error) {
	body := map[string]string{
		"provider":      provider,
		"role_id":       role,
		"category_id":   category,
		"group_id":      group,
		"user_uid":      uid,
		"user_username": username,
		"password":      pwd,
	}

	req, err := c.newJSONRequest(http.MethodPost, "admin/user", body)
	if err != nil {
		return nil, err
	}

	usr := &User{}
	if _, err := c.do(ctx, req, usr); err != nil {
		return nil, fmt.Errorf("create user: %w", err)
	}

	return usr, nil
}

type Group struct {
	ID            *string `json:"id,omitempty"`
	UID           *string `json:"uid,omitempty"`
	Category      *string `json:"parent_category,omitempty"`
	Name          *string `json:"name,omitempty"`
	Description   *string `json:"description,omitempty"`
	ExternalAppID *string `json:"external_app_id,omitempty"`
	ExternalGID   *string `json:"external_gid,omitempty"`
}

func (c *Client) AdminGroupCreate(ctx context.Context, category, uid, name, description, externalAppID, externalGID string) (*Group, error) {
	g := &Group{
		UID:           &uid,
		Category:      &category,
		Name:          &name,
		Description:   &description,
		ExternalAppID: &externalAppID,
		ExternalGID:   &externalGID,
	}

	req, err := c.newJSONRequest(http.MethodPost, "admin/group", g)
	if err != nil {
		return nil, err
	}

	grp := &Group{}
	if _, err := c.do(ctx, req, grp); err != nil {
		return nil, fmt.Errorf("create group: %w", err)
	}

	return grp, nil
}

func (c *Client) AdminUserDelete(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("admin/user/%s", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("delete user '%s': %w", id, err)
	}

	return nil
}

// TODO: This should be removed when the admin/domains endpoint and the user/desktops endpoints are unified
type AdminDesktop struct {
	ID                *string `json:"id,omitempty"`
	State             *string `json:"status,omitempty"`
	Name              *string `json:"name,omitempty"`
	Description       *string `json:"description,omitempty"`
	User              *string `json:"user,omitempty"`
	HypervisorStarted *string `json:"hyp_started,omitempty"`
}

type adminDesktop struct {
	ID    *string `json:"id,omitempty"`
	State *string `json:"status,omitempty"`
	// Type        *string `json:"type,omitempty"`
	// Template    *string `json:"template,omitempty"`
	Name        *string `json:"name,omitempty"`
	Description *string `json:"description,omitempty"`
	User        *string `json:"user,omitempty"`
	// IP          *string `json:"ip,omitempty"`
	HypervisorStarted hyperStarted `json:"hyp_started,omitempty"`
}

type hyperStarted struct {
	Started *string
}

func (h *hyperStarted) UnmarshalJSON(data []byte) error {
	if string(data) == "false" || string(data) == `""` || string(data) == "null" {
		h.Started = nil
		return nil
	}

	var s *string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}

	h.Started = s
	return nil
}

func (c *Client) AdminDesktopList(ctx context.Context) ([]*AdminDesktop, error) {
	req, err := c.newRequest(http.MethodGet, "admin/domains?kind=desktop", nil)
	if err != nil {
		return nil, err
	}

	desktopsJSON := []*adminDesktop{}
	if _, err = c.do(ctx, req, &desktopsJSON); err != nil {
		return nil, fmt.Errorf("desktop list: %w", err)
	}

	desktops := []*AdminDesktop{}
	for _, d := range desktopsJSON {
		desktops = append(desktops, &AdminDesktop{
			ID:                d.ID,
			State:             d.State,
			Name:              d.Name,
			Description:       d.Description,
			User:              d.User,
			HypervisorStarted: d.HypervisorStarted.Started,
		})
	}

	return desktops, nil
}

func (c *Client) AdminTemplateList(ctx context.Context) ([]*Template, error) {
	req, err := c.newRequest(http.MethodGet, "admin/domains?kind=template", nil)
	if err != nil {
		return nil, err
	}

	var templates = []*Template{}
	if _, err = c.do(ctx, req, &templates); err != nil {
		return nil, fmt.Errorf("template list: %w", err)
	}

	return templates, nil
}

func (c *Client) AdminHypervisorUpdate(ctx context.Context, h *Hypervisor) error {
	req, err := c.newJSONRequest(http.MethodPut, "admin/table/update/hypervisors", h)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("update hypervisor: %w", err)
	}

	return nil
}

func (c *Client) AdminHypervisorOnlyForced(ctx context.Context, id string, onlyForced bool) error {
	return c.AdminHypervisorUpdate(ctx, &Hypervisor{
		ID:         &id,
		OnlyForced: &onlyForced,
	})
}

func (c *Client) AdminUserRequiredDisclaimerAcknowledgement(ctx context.Context, id string) (bool, error) {
	req, err := c.newJSONRequest(http.MethodGet, fmt.Sprintf("admin/user/required/disclaimer-acknowledgement/%s", id), nil)
	if err != nil {
		return false, err
	}

	rsp := struct {
		Required *bool `json:"required,omitempty"`
	}{}
	if _, err := c.do(ctx, req, &rsp); err != nil {
		return false, fmt.Errorf("check admin user required disclaimer acknowledgement: %w", err)
	}

	return *rsp.Required, nil
}

func (c *Client) AdminUserRequiredEmailVerification(ctx context.Context, id string) (bool, error) {
	req, err := c.newJSONRequest(http.MethodGet, fmt.Sprintf("admin/user/required/email-verification/%s", id), nil)
	if err != nil {
		return false, err
	}

	rsp := struct {
		Required *bool `json:"required,omitempty"`
	}{}
	if _, err := c.do(ctx, req, &rsp); err != nil {
		return false, fmt.Errorf("check admin user required email verification: %w", err)
	}

	return *rsp.Required, nil
}

func (c *Client) AdminUserRequiredPasswordReset(ctx context.Context, id string) (bool, error) {
	req, err := c.newJSONRequest(http.MethodGet, fmt.Sprintf("admin/user/required/password-reset/%s", id), nil)
	if err != nil {
		return false, err
	}

	rsp := struct {
		Required *bool `json:"required,omitempty"`
	}{}
	if _, err := c.do(ctx, req, &rsp); err != nil {
		return false, fmt.Errorf("check admin user required password reset: %w", err)
	}

	return *rsp.Required, nil
}
