package isardvdi

import (
	"context"
	"fmt"
	"net/http"
)

type StatsCategory struct {
	ID          *string
	DesktopNum  *int
	TemplateNum *int
	UserNum     *int
}

type statsCategoryListRsp struct {
	Desktops  statsCategoryListDesktopsRsp  `json:"desktops"`
	Tempaltes statsCategoryListTemplatesRsp `json:"templates"`
	Users     statsCategoryListUsersRsp     `json:"users"`
}

type statsCategoryListDesktopsRsp struct {
	Total int `json:"total"`
}

type statsCategoryListTemplatesRsp struct {
	Total int `json:"total"`
}

type statsCategoryListUsersRsp struct {
	Total int `json:"total"`
}

func (c *Client) StatsCategoryList(ctx context.Context) ([]*StatsCategory, error) {
	req, err := c.newRequest(http.MethodGet, "stats/categories", nil)
	if err != nil {
		return nil, err
	}

	categories := struct {
		Category map[string]statsCategoryListRsp `json:"category"`
	}{}
	if _, err := c.do(ctx, req, &categories); err != nil {
		return nil, fmt.Errorf("stats category list: %w", err)
	}

	rsp := []*StatsCategory{}
	for k, v := range categories.Category {
		// We need to make a copy, otherwise it's always going to point to the same mem address and every rsp entry is going to have the same values
		id := k
		c := v

		rsp = append(rsp, &StatsCategory{
			ID:          &id,
			DesktopNum:  &c.Desktops.Total,
			TemplateNum: &c.Tempaltes.Total,
			UserNum:     &c.Users.Total,
		})
	}

	return rsp, nil
}

type StatsDeploymentByCategory struct {
	CategoryID    *string
	DeploymentNum *int
}

func (c *Client) StatsDeploymentByCategory(ctx context.Context) ([]*StatsDeploymentByCategory, error) {
	req, err := c.newRequest(http.MethodGet, "stats/categories/deployments", nil)
	if err != nil {
		return nil, err
	}

	deployments := struct {
		Categories map[string]int `json:"categories"`
	}{}
	if _, err := c.do(ctx, req, &deployments); err != nil {
		return nil, fmt.Errorf("stats deployments by category: %w", err)
	}

	rsp := []*StatsDeploymentByCategory{}
	for k, v := range deployments.Categories {
		// We need to make a copy, otherwise it's always going to point to the same mem address and every rsp entry is going to have the same values
		id := k
		i := v

		rsp = append(rsp, &StatsDeploymentByCategory{
			CategoryID:    &id,
			DeploymentNum: &i,
		})
	}

	return rsp, nil
}

type StatsUser struct {
	ID       *string `json:"id,omitempty"`
	Role     *string `json:"role,omitempty"`
	Category *string `json:"category,omitempty"`
	Group    *string `json:"group,omitempty"`
}

func (c *Client) StatsUsers(ctx context.Context) ([]*StatsUser, error) {
	req, err := c.newRequest(http.MethodGet, "stats/users", nil)
	if err != nil {
		return nil, err
	}

	u := []*StatsUser{}
	if _, err := c.do(ctx, req, &u); err != nil {
		return nil, fmt.Errorf("get user stats: %w", err)
	}

	return u, nil
}

type StatsDesktop struct {
	ID   *string `json:"id,omitempty"`
	User *string `json:"user,omitempty"`
}

func (c *Client) StatsDesktops(ctx context.Context) ([]*StatsDesktop, error) {
	req, err := c.newRequest(http.MethodGet, "stats/desktops", nil)
	if err != nil {
		return nil, err
	}

	d := []*StatsDesktop{}
	if _, err := c.do(ctx, req, &d); err != nil {
		return nil, fmt.Errorf("get desktop stats: %w", err)
	}

	return d, nil
}

type StatsTemplate struct {
	ID *string `json:"id,omitempty"`
}

func (c *Client) StatsTemplates(ctx context.Context) ([]*StatsTemplate, error) {
	req, err := c.newRequest(http.MethodGet, "stats/templates", nil)
	if err != nil {
		return nil, err
	}

	t := []*StatsTemplate{}
	if _, err := c.do(ctx, req, &t); err != nil {
		return nil, fmt.Errorf("get template stats: %w", err)
	}

	return t, nil
}

type StatsHypervisor struct {
	ID         *string           `json:"id,omitempty"`
	Status     *HypervisorStatus `json:"status,omitempty"`
	OnlyForced *bool             `json:"only_forced,omitempty"`
}

func (c *Client) StatsHypervisors(ctx context.Context) ([]*StatsHypervisor, error) {
	req, err := c.newRequest(http.MethodGet, "stats/hypervisors", nil)
	if err != nil {
		return nil, err
	}

	h := []*StatsHypervisor{}
	if _, err := c.do(ctx, req, &h); err != nil {
		return nil, fmt.Errorf("get template stats: %w", err)
	}

	return h, nil
}

type StatsDomainsStatus struct {
	Desktop  map[DomainState]int `json:"desktop,omitempty"`
	Template map[DomainState]int `json:"template,omitempty"`
}

func (c *Client) StatsDomainsStatus(ctx context.Context) (*StatsDomainsStatus, error) {
	req, err := c.newRequest(http.MethodGet, "stats/domains/status", nil)
	if err != nil {
		return nil, err
	}

	s := &StatsDomainsStatus{}
	if _, err := c.do(ctx, req, s); err != nil {
		return nil, fmt.Errorf("get domains status stats: %w", err)
	}

	return s, nil
}
