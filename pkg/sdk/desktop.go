package isardvdi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
)

type Desktop struct {
	ID          *string      `json:"id,omitempty"`
	State       *DomainState `json:"state,omitempty"`
	Type        *string      `json:"type,omitempty"`
	Template    *string      `json:"template,omitempty"`
	Name        *string      `json:"name,omitempty"`
	Description *string      `json:"description,omitempty"`
	IP          *string      `json:"ip,omitempty"`
}

type DesktopViewer string

const (
	DesktopViewerSpice      DesktopViewer = "spice"
	DesktopViewerVNCBrowser DesktopViewer = "vnc-browser"
	DesktopViewerRdpGW      DesktopViewer = "rdp-gw"
	DesktopViewerRdpVPN     DesktopViewer = "rdp-vpn"
	DesktopViewerRdpBrowser DesktopViewer = "rdp-browser"
)

type DesktopViewerRsp struct {
	Kind     *string `json:"kind,omitempty"`
	Protocol *string `json:"protocol,omitempty"`
	URLP     *string `json:"urlp,omitempty"`
	Cookie   *string `json:"cookie,omitempty"`
	Content  *string `json:"content,omitempty"`
}

func (c *Client) DesktopList(ctx context.Context) ([]*Desktop, error) {
	req, err := c.newRequest(http.MethodGet, "user/desktops", nil)
	if err != nil {
		return nil, err
	}

	var desktops = []*Desktop{}
	if _, err = c.do(ctx, req, &desktops); err != nil {
		return nil, fmt.Errorf("desktop list: %w", err)
	}

	return desktops, nil
}

func (c *Client) DesktopGet(ctx context.Context, id string) (*Desktop, error) {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("user/desktop/%s", id), nil)
	if err != nil {
		return nil, err
	}

	d := &Desktop{}
	if _, err := c.do(ctx, req, d); err != nil {
		return nil, fmt.Errorf("get desktop: %w", err)
	}

	return d, nil
}

func (c *Client) DesktopCreate(ctx context.Context, name, templateID string) (*Desktop, error) {
	body := map[string]string{
		"name":        name,
		"template_id": templateID,
	}

	req, err := c.newJSONRequest(http.MethodPost, "persistent_desktop", body)
	if err != nil {
		return nil, err
	}

	d := &Desktop{}
	if _, err = c.do(ctx, req, d); err != nil {
		return nil, fmt.Errorf("create desktop: %w", err)
	}

	return d, nil
}

func (c *Client) DesktopCreateFromScratch(ctx context.Context, name string, xml string) (*Desktop, error) {
	u, err := addOptions("desktop/from/scratch", map[string]string{
		"name": name,
		"xml":  xml,
	})
	if err != nil {
		return nil, err
	}

	req, err := c.newRequest(http.MethodPost, u, nil)
	if err != nil {
		return nil, err
	}

	d := &Desktop{}
	if _, err := c.do(ctx, req, d); err != nil {
		return nil, fmt.Errorf("create desktop: %w", err)
	}

	return d, nil
}

func (c *Client) DesktopDelete(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("desktop/%s", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("delete desktop: %w", err)
	}

	return nil
}

func (c *Client) DesktopStart(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("desktop/start/%s", id), nil)
	if err != nil {
		return nil
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("start desktop: %w", err)
	}

	return nil
}

func (c *Client) DesktopStop(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("desktop/stop/%s", id), nil)
	if err != nil {
		return nil
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("stop desktop: %w", err)
	}

	return nil
}

func (c *Client) DesktopViewer(ctx context.Context, t DesktopViewer, id string) (string, error) {
	switch t {
	case DesktopViewerSpice:
		t = "file-spice"
	case DesktopViewerVNCBrowser:
		t = "browser-vnc"
	case DesktopViewerRdpGW:
		t = "file-rdpgw"
	case DesktopViewerRdpVPN:
		t = "file-rdpvpn"
	case DesktopViewerRdpBrowser:
		t = "browser-rdp"

	default:
		return "", fmt.Errorf("unknown viewer type: %s", t)
	}

	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("desktop/%s/viewer/%s", id, t), nil)
	if err != nil {
		return "", nil
	}

	rsp := &DesktopViewerRsp{}
	if _, err := c.do(ctx, req, rsp); err != nil {
		return "", fmt.Errorf("get desktop viewer: %w", err)
	}

	if rsp.Kind == nil {
		return "", errors.New("empty response kind")
	}

	switch *rsp.Kind {
	case "file":
		if rsp.Content == nil {
			return "", errors.New("empty response content")
		}

		return *rsp.Content, nil

	case "browser":
		if rsp.URLP == nil {
			return "", errors.New("empty response URL")
		}

		return *rsp.URLP, nil

	default:
		return "", errors.New("unknown response kind")
	}
}

type DesktopUpdateOptions struct {
	ForcedHyp []string `json:"forced_hyp,omitempty"`
}

func (c *Client) DesktopUpdate(ctx context.Context, id string, opts DesktopUpdateOptions) error {
	b, err := json.Marshal(opts)
	if err != nil {
		return err
	}

	req, err := c.newRequest(http.MethodPut, fmt.Sprintf("desktop/%s", id), nil)
	if err != nil {
		return err
	}

	req.Body = io.NopCloser(bytes.NewBuffer(b))
	req.Header.Set("Content-Type", "application/json")

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("update desktop: %w", err)
	}

	return nil
}
