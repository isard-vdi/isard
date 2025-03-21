package sdk

import (
	"context"
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
func (c *Client) AdminUserResetPassword(ctx context.Context, id, pwd string) error {
	body := map[string]string{
		"user_id":  id,
		"password": pwd,
	}

	req, err := c.newJSONRequest(http.MethodPut, "admin/user/reset-password", body)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("reset user password: %w", err)
	}

	return nil
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

func (c *Client) AdminUserAutoRegister(ctx context.Context, registerTkn string, roleID string, groupID string, secondaryGroupsIDs []string) (string, error) {
	body := map[string]interface{}{
		"role_id":  roleID,
		"group_id": groupID,
	}

	if secondaryGroupsIDs != nil {
		body["secondary_groups"] = secondaryGroupsIDs
	}

	req, err := c.newJSONRequest(http.MethodPost, "admin/user/auto-register", body)
	if err != nil {
		return "", err
	}

	req.Header.Add("Register-Claims", fmt.Sprintf("Bearer %s", registerTkn))

	rsp := struct {
		ID *string `json:"id,omitempty"`
	}{}

	if _, err := c.do(ctx, req, &rsp); err != nil {
		return "", fmt.Errorf("auto register the user: %w", err)
	}

	return *rsp.ID, nil
}

func (c *Client) AdminUserNotificationsDisplays(ctx context.Context, id string) ([]string, error) {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("admin/notifications/user/displays/%s/login", id), nil)
	if err != nil {
		return nil, err
	}

	rsp := struct {
		Displays []string `json:"displays,omitempty"`
	}{}
	if _, err := c.do(ctx, req, &rsp); err != nil {
		return nil, fmt.Errorf("get user notification display: %w", err)
	}

	return rsp.Displays, nil
}
