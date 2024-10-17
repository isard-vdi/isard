package sdk

import (
	"context"
	"fmt"
	"net/http"
)

type HypervisorStatus string

const (
	HypervisorStatusOnline   HypervisorStatus = "Online"
	HypervisorStatusOffline  HypervisorStatus = "Offline"
	HypervisorStatusError    HypervisorStatus = "Error"
	HypervisorStatusDeleting HypervisorStatus = "Deleting"
)

type Hypervisor struct {
	ID         *string           `json:"id,omitempty"`
	URI        *string           `json:"uri,omitempty"`
	Status     *HypervisorStatus `json:"status,omitempty"`
	OnlyForced *bool             `json:"only_forced,omitempty"`
	Buffering  *bool             `json:"buffering_hyper,omitempty"`
}

func (c *Client) HypervisorList(ctx context.Context) ([]*Hypervisor, error) {
	req, err := c.newRequest(http.MethodGet, "hypervisors", nil)
	if err != nil {
		return nil, err
	}

	hypervisors := []*Hypervisor{}
	if _, err = c.do(ctx, req, &hypervisors); err != nil {
		return nil, fmt.Errorf("hypervisor list: %w", err)
	}

	return hypervisors, nil
}

func (c *Client) HypervisorGet(ctx context.Context, id string) (*Hypervisor, error) {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("hypervisor/%s", id), nil)
	if err != nil {
		return nil, err
	}

	hyper := &Hypervisor{}
	if _, err := c.do(ctx, req, hyper); err != nil {
		return nil, fmt.Errorf("get hypervisor: %w", err)
	}

	return hyper, nil
}

func (c *Client) HypervisorDelete(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("hypervisor/%s", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("delete hypervisor: %w", err)
	}

	return nil
}
