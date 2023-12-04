package mock

import (
	"context"
	"net/url"
	"time"

	"github.com/stretchr/testify/mock"
	"gitlab.com/isard/isardvdi-sdk-go"
)

type Client struct {
	mock.Mock
}

var _ isardvdi.Interface = &Client{}

func (c *Client) SetBeforeRequestHook(hook func(*isardvdi.Client) error) {
	c.Called(hook)
}

func (c *Client) URL() *url.URL {
	return nil
}

func (c *Client) Version(ctx context.Context) (string, error) {
	args := c.Called(ctx)
	return args.String(0), args.Error(1)
}

func (c *Client) Maintenance(ctx context.Context) (bool, error) {
	args := c.Called(ctx)
	return args.Bool(0), args.Error(1)
}

func (c *Client) SetToken(tkn string) {
	c.Called(tkn)
}

func (c *Client) AuthForm(ctx context.Context, category, usr, pwd string) (string, error) {
	args := c.Called(ctx, category, usr, pwd)
	return args.String(0), args.Error(1)
}

func (c *Client) UserVPN(ctx context.Context) (string, error) {
	args := c.Called(ctx)
	return args.String(0), args.Error(1)
}

func (c *Client) UserOwnsDesktop(ctx context.Context, opts *isardvdi.UserOwnsDesktopOpts) error {
	args := c.Called(ctx, opts)
	return args.Error(0)
}

func (c *Client) AdminUserList(ctx context.Context) ([]*isardvdi.User, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.User), args.Error(1)
}

func (c *Client) AdminUserCreate(ctx context.Context, provider, role, category, group, uid, username, pwd string) (*isardvdi.User, error) {
	args := c.Called(ctx, provider, role, category, group, uid, username, pwd)
	return args.Get(0).(*isardvdi.User), args.Error(1)
}

func (c *Client) AdminUserDelete(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) AdminUserResetPassword(ctx context.Context, id, pwd string) error {
	args := c.Called(ctx, id, pwd)
	return args.Error(0)
}

func (c *Client) AdminUserRequiredDisclaimerAcknowledgement(ctx context.Context, id string) (bool, error) {
	args := c.Called(ctx, id)
	return args.Bool(0), args.Error(1)
}

func (c *Client) AdminUserRequiredEmailVerification(ctx context.Context, id string) (bool, error) {
	args := c.Called(ctx, id)
	return args.Bool(0), args.Error(1)
}

func (c *Client) AdminUserRequiredPasswordReset(ctx context.Context, id string) (bool, error) {
	args := c.Called(ctx, id)
	return args.Bool(0), args.Error(1)
}

func (c *Client) AdminGroupCreate(ctx context.Context, category, uid, name, description, externalAppID, externalGID string) (*isardvdi.Group, error) {
	args := c.Called(ctx, category, uid, name, description, externalAppID, externalGID)
	return args.Get(0).(*isardvdi.Group), args.Error(1)
}

func (c *Client) AdminDesktopList(ctx context.Context) ([]*isardvdi.AdminDesktop, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.AdminDesktop), args.Error(1)
}

func (c *Client) AdminTemplateList(ctx context.Context) ([]*isardvdi.Template, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.Template), args.Error(1)
}

func (c *Client) AdminHypervisorUpdate(ctx context.Context, hyp *isardvdi.Hypervisor) error {
	args := c.Called(ctx, hyp)
	return args.Error(0)
}

func (c *Client) AdminHypervisorOnlyForced(ctx context.Context, id string, onlyForced bool) error {
	args := c.Called(ctx, id, onlyForced)
	return args.Error(0)
}

func (c *Client) HypervisorList(ctx context.Context) ([]*isardvdi.Hypervisor, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.Hypervisor), args.Error(1)
}

func (c *Client) HypervisorGet(ctx context.Context, id string) (*isardvdi.Hypervisor, error) {
	args := c.Called(ctx, id)
	return args.Get(0).(*isardvdi.Hypervisor), args.Error(1)
}

func (c *Client) HypervisorDelete(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) DesktopList(ctx context.Context) ([]*isardvdi.Desktop, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.Desktop), args.Error(1)
}

func (c *Client) DesktopGet(ctx context.Context, id string) (*isardvdi.Desktop, error) {
	args := c.Called(ctx, id)
	return args.Get(0).(*isardvdi.Desktop), args.Error(1)
}

func (c *Client) DesktopCreate(ctx context.Context, name, templateID string) (*isardvdi.Desktop, error) {
	args := c.Called(ctx, name, templateID)
	return args.Get(0).(*isardvdi.Desktop), args.Error(1)
}

func (c *Client) DesktopCreateFromScratch(ctx context.Context, name, xml string) (*isardvdi.Desktop, error) {
	args := c.Called(ctx, name, xml)
	return args.Get(0).(*isardvdi.Desktop), args.Error(1)
}

func (c *Client) DesktopUpdate(ctx context.Context, id string, opts isardvdi.DesktopUpdateOptions) error {
	args := c.Called(ctx, id, opts)
	return args.Error(0)
}

func (c *Client) DesktopDelete(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) DesktopStart(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) DesktopStop(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) DesktopViewer(ctx context.Context, t isardvdi.DesktopViewer, id string) (string, error) {
	args := c.Called(ctx, t, id)
	return args.String(0), args.Error(0)
}

func (c *Client) TemplateList(ctx context.Context) ([]*isardvdi.Template, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.Template), args.Error(1)
}

func (c *Client) TemplateCreateFromDesktop(ctx context.Context, name, desktopID string) (*isardvdi.Template, error) {
	args := c.Called(ctx, name, desktopID)
	return args.Get(0).(*isardvdi.Template), args.Error(1)
}

func (c *Client) StatsCategoryList(ctx context.Context) ([]*isardvdi.StatsCategory, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsCategory), args.Error(1)
}

func (c *Client) StatsDeploymentByCategory(ctx context.Context) ([]*isardvdi.StatsDeploymentByCategory, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsDeploymentByCategory), args.Error(1)
}

func (c *Client) StatsUsers(ctx context.Context) ([]*isardvdi.StatsUser, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsUser), args.Error(1)
}

func (c *Client) StatsDesktops(ctx context.Context) ([]*isardvdi.StatsDesktop, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsDesktop), args.Error(1)
}

func (c *Client) StatsTemplates(ctx context.Context) ([]*isardvdi.StatsTemplate, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsTemplate), args.Error(1)
}

func (c *Client) StatsHypervisors(ctx context.Context) ([]*isardvdi.StatsHypervisor, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.StatsHypervisor), args.Error(1)
}

func (c *Client) StatsDomainsStatus(ctx context.Context) (*isardvdi.StatsDomainsStatus, error) {
	args := c.Called(0)
	return args.Get(0).(*isardvdi.StatsDomainsStatus), args.Error(1)
}

func (c *Client) OrchestratorHypervisorList(ctx context.Context) ([]*isardvdi.OrchestratorHypervisor, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.OrchestratorHypervisor), args.Error(1)
}
func (c *Client) OrchestratorHypervisorGet(ctx context.Context, id string) (*isardvdi.OrchestratorHypervisor, error) {
	args := c.Called(ctx, id)
	return args.Get(0).(*isardvdi.OrchestratorHypervisor), args.Error(1)
}
func (c *Client) OrchestratorHypervisorManage(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}
func (c *Client) OrchestratorHypervisorUnmanage(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}
func (c *Client) OrchestratorHypervisorAddToDeadRow(ctx context.Context, id string) (time.Time, error) {
	args := c.Called(ctx, id)
	return args.Get(0).(time.Time), args.Error(1)
}
func (c *Client) OrchestratorHypervisorRemoveFromDeadRow(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}
func (c *Client) OrchestratorHypervisorStopDesktops(ctx context.Context, id string) error {
	args := c.Called(ctx, id)
	return args.Error(0)
}

func (c *Client) OrchestratorGPUBookingList(ctx context.Context) ([]*isardvdi.OrchestratorGPUBooking, error) {
	args := c.Called(ctx)
	return args.Get(0).([]*isardvdi.OrchestratorGPUBooking), args.Error(1)
}
