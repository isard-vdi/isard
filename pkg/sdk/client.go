package isardvdi

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"time"

	"github.com/google/go-querystring/query"
)

var _ Interface = &Client{}

type Client struct {
	BaseURL   *url.URL
	UserAgent string
	Token     string

	BeforeRequestHook func(*Client) error

	httpClient *http.Client
}

type Interface interface {
	URL() *url.URL

	Version(context.Context) (string, error)
	Maintenance(context.Context) (bool, error)

	SetBeforeRequestHook(func(*Client) error)

	AuthForm(ctx context.Context, category, usr, pwd string) (string, error)
	SetToken(string)

	UserVPN(context.Context) (string, error)
	UserOwnsDesktop(context.Context, *UserOwnsDesktopOpts) error

	AdminUserList(ctx context.Context) ([]*User, error)
	AdminUserCreate(ctx context.Context, provider, role, category, group, uid, username, pwd string) (*User, error)
	AdminUserDelete(ctx context.Context, id string) error
	AdminUserResetPassword(ctx context.Context, id, pwd string) error
	AdminUserRequiredDisclaimerAcknowledgement(ctx context.Context, id string) (bool, error)
	AdminUserRequiredEmailVerification(ctx context.Context, id string) (bool, error)
	AdminUserRequiredPasswordReset(ctx context.Context, id string) (bool, error)
	AdminUserAutoRegister(ctx context.Context, registerTkn, roleID, groupID string) (id string, err error)

	AdminGroupCreate(ctx context.Context, category, uid, name, description, externalAppID, externalGID string) (*Group, error)
	AdminDesktopList(context.Context) ([]*AdminDesktop, error)
	AdminTemplateList(context.Context) ([]*Template, error)
	AdminHypervisorUpdate(context.Context, *Hypervisor) error
	AdminHypervisorOnlyForced(ctx context.Context, id string, onlyForced bool) error

	HypervisorList(context.Context) ([]*Hypervisor, error)
	HypervisorGet(ctx context.Context, id string) (*Hypervisor, error)
	HypervisorDelete(ctx context.Context, id string) error

	DesktopList(context.Context) ([]*Desktop, error)
	DesktopGet(ctx context.Context, id string) (*Desktop, error)
	DesktopCreate(ctx context.Context, name, templateID string) (*Desktop, error)
	DesktopCreateFromScratch(ctx context.Context, name, xml string) (*Desktop, error)
	DesktopUpdate(ctx context.Context, id string, opts DesktopUpdateOptions) error
	DesktopDelete(ctx context.Context, id string) error
	DesktopStart(ctx context.Context, id string) error
	DesktopStop(ctx context.Context, id string) error
	DesktopViewer(ctx context.Context, t DesktopViewer, id string) (string, error)

	TemplateList(context.Context) ([]*Template, error)
	TemplateCreateFromDesktop(ctx context.Context, name, desktopID string) (*Template, error)

	StatsCategoryList(context.Context) ([]*StatsCategory, error)
	StatsDeploymentByCategory(ctx context.Context) ([]*StatsDeploymentByCategory, error)
	StatsUsers(ctx context.Context) ([]*StatsUser, error)
	StatsDesktops(ctx context.Context) ([]*StatsDesktop, error)
	StatsTemplates(ctx context.Context) ([]*StatsTemplate, error)
	StatsHypervisors(ctx context.Context) ([]*StatsHypervisor, error)
	StatsDomainsStatus(ctx context.Context) (*StatsDomainsStatus, error)

	OrchestratorHypervisorList(ctx context.Context) ([]*OrchestratorHypervisor, error)
	OrchestratorHypervisorGet(ctx context.Context, id string) (*OrchestratorHypervisor, error)
	OrchestratorHypervisorManage(ctx context.Context, id string) error
	OrchestratorHypervisorUnmanage(ctx context.Context, id string) error
	OrchestratorHypervisorAddToDeadRow(ctx context.Context, id string) (time.Time, error)
	OrchestratorHypervisorRemoveFromDeadRow(ctx context.Context, id string) error
	OrchestratorHypervisorStopDesktops(ctx context.Context, id string) error
	OrchestratorGPUBookingList(ctx context.Context) ([]*OrchestratorGPUBooking, error)
}

func NewClient(cfg *Cfg) (*Client, error) {
	u, err := url.Parse(cfg.Host)
	if err != nil {
		return nil, fmt.Errorf("invalid base URL: %w", err)
	}

	u.Path = "/api/v3/"

	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: cfg.IgnoreCerts},
	}

	http.DefaultClient.Transport = tr

	c := &Client{
		BaseURL:    u,
		UserAgent:  fmt.Sprintf("isardvdi-sdk-go %s", Version),
		Token:      cfg.Token,
		httpClient: http.DefaultClient,
	}

	c.SetBeforeRequestHook(func(c *Client) error {
		return nil
	})

	return c, nil
}

func (c *Client) SetBeforeRequestHook(hook func(*Client) error) {
	c.BeforeRequestHook = hook
}

func (c *Client) newRequest(method, path string, body url.Values) (*http.Request, error) {
	if err := c.BeforeRequestHook(c); err != nil {
		return nil, fmt.Errorf("before request hook: %w", err)
	}

	rel, err := url.Parse(path)
	if err != nil {
		return nil, fmt.Errorf("parse URL path: %w", err)
	}

	u := c.BaseURL.ResolveReference(rel)

	var buf io.Reader
	if body != nil {
		buf = strings.NewReader(body.Encode())
	}

	req, err := http.NewRequest(method, u.String(), buf)
	if err != nil {
		return nil, fmt.Errorf("create HTTP request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.UserAgent)
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	return req, nil
}

func (c *Client) newFormData(method, path string, body url.Values) (*http.Request, error) {
	if err := c.BeforeRequestHook(c); err != nil {
		return nil, fmt.Errorf("before request hook: %w", err)
	}

	rel, err := url.Parse(path)
	if err != nil {
		return nil, fmt.Errorf("parse URL path: %w", err)
	}

	u := c.BaseURL.ResolveReference(rel)

	buf := &bytes.Buffer{}
	form := multipart.NewWriter(buf)

	if body != nil {
		for k, v := range body {
			if err := form.WriteField(k, v[0]); err != nil {
				return nil, fmt.Errorf("write the form field '%s': %w", k, err)
			}
		}

		if err := form.Close(); err != nil {
			return nil, fmt.Errorf("close the form: %w", err)
		}
	}

	req, err := http.NewRequest(method, u.String(), buf)
	if err != nil {
		return nil, fmt.Errorf("create HTTP request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", form.FormDataContentType())
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.UserAgent)
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	return req, nil
}

func (c *Client) newJSONRequest(method, path string, body interface{}) (*http.Request, error) {
	if err := c.BeforeRequestHook(c); err != nil {
		return nil, fmt.Errorf("before request hook: %w", err)
	}

	rel, err := url.Parse(path)
	if err != nil {
		return nil, fmt.Errorf("parse URL path: %w", err)
	}

	u := c.BaseURL.ResolveReference(rel)

	var buf io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("marshal JSON body: %w", err)
		}

		buf = bytes.NewBuffer(b)
	}

	req, err := http.NewRequest(method, u.String(), buf)
	if err != nil {
		return nil, fmt.Errorf("create HTTP request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.UserAgent)
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	return req, nil
}

func (c *Client) do(ctx context.Context, req *http.Request, v interface{}) (*http.Response, error) {
	req = req.WithContext(ctx)

	rsp, err := c.httpClient.Do(req)
	if err != nil {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
		}

		return nil, fmt.Errorf("do HTTP request: %w", err)
	}
	defer rsp.Body.Close()

	teeReader := &bytes.Buffer{}
	errReader := io.TeeReader(rsp.Body, teeReader)
	rsp.Body = io.NopCloser(teeReader)

	errRsp := &Err{}
	_ = json.NewDecoder(errReader).Decode(errRsp)

	if errRsp.Err != "" && errRsp.Msg != "" {
		errRsp.StatusCode = rsp.StatusCode

		return rsp, errRsp
	}

	if rsp.StatusCode == http.StatusServiceUnavailable {
		return rsp, ErrMaintenance
	}

	// TODO: Should we react to more non 200 codes? (>=500)
	if rsp.StatusCode >= http.StatusInternalServerError {
		return rsp, fmt.Errorf("unexpected http code: %d", rsp.StatusCode)
	}

	if v != nil {
		body := &bytes.Buffer{}
		jsonReader := io.TeeReader(teeReader, body)
		rsp.Body = io.NopCloser(body)

		if err := json.NewDecoder(jsonReader).Decode(v); err != nil {
			return rsp, fmt.Errorf("decode JSON response: %w", err)
		}
	}

	return rsp, nil
}

func addOptions(s string, opt interface{}) (string, error) {
	v := reflect.ValueOf(opt)
	if v.Kind() == reflect.Ptr && v.IsNil() {
		return s, nil
	}

	u, err := url.Parse(s)
	if err != nil {
		return s, err
	}

	vs := url.Values{}
	t := reflect.TypeOf(opt)
	if t.Kind() == reflect.Map {
		opts := opt.(map[string]string)
		for k, v := range opts {
			vs.Set(k, v)
		}

	} else {
		vs, err = query.Values(opt)
		if err != nil {
			return s, err
		}
	}

	u.RawQuery = vs.Encode()

	return u.String(), nil
}

func (c *Client) URL() *url.URL {
	return c.BaseURL
}

type versionRsp struct {
	Version string `json:"isardvdi_version"`
}

func (c *Client) Version(ctx context.Context) (string, error) {
	req, err := c.newRequest(http.MethodGet, "", nil)
	if err != nil {
		return "", err
	}

	i := &versionRsp{}
	if _, err := c.do(ctx, req, i); err != nil {
		return "", fmt.Errorf("get IsardVDI version: %w", err)
	}

	return i.Version, nil
}

func (c *Client) Maintenance(ctx context.Context) (bool, error) {
	req, err := c.newRequest(http.MethodGet, "maintenance", nil)
	if err != nil {
		return false, err
	}

	m := false
	if _, err := c.do(ctx, req, &m); err != nil {
		return false, fmt.Errorf("get IsardVDI maintenance status: %w", err)
	}

	return m, nil
}
