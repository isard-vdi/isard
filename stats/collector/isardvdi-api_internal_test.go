package collector

import (
	"strings"
	"testing"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
)

func TestIsardVDIAPICollect(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Hypervisors apiv4.StatsHypervisorsOKApplicationJSON
		Connected   apiv4.StatsConnectedUsersResponse
		Metric      string
		Expected    string
	}{
		"should export the distinct connected users": {
			Connected: apiv4.StatsConnectedUsersResponse{Users: 2, Sockets: 5},
			Metric:    "isardvdi_isardvdi_api_connected_users",
			Expected: `
# HELP isardvdi_isardvdi_api_connected_users Number of distinct users with at least one live Socket.IO connection
# TYPE isardvdi_isardvdi_api_connected_users gauge
isardvdi_isardvdi_api_connected_users 2
`,
		},
		"should export the live sockets": {
			Connected: apiv4.StatsConnectedUsersResponse{Users: 2, Sockets: 5},
			Metric:    "isardvdi_isardvdi_api_connected_sockets",
			Expected: `
# HELP isardvdi_isardvdi_api_connected_sockets Number of live Socket.IO connections, one per browser tab and namespace
# TYPE isardvdi_isardvdi_api_connected_sockets gauge
isardvdi_isardvdi_api_connected_sockets 5
`,
		},
		"should label the desktops as desktop in the domain status": {
			Metric: "isardvdi_isardvdi_api_domain_status",
			Expected: `
# HELP isardvdi_isardvdi_api_domain_status Information of the number of domains of a domain type that have a specific status
# TYPE isardvdi_isardvdi_api_domain_status gauge
isardvdi_isardvdi_api_domain_status{status="Started",type="desktop"} 3
isardvdi_isardvdi_api_domain_status{status="Stopped",type="template"} 2
`,
		},
		"should export a degraded online hypervisor with the family of the reason": {
			Hypervisors: apiv4.StatsHypervisorsOKApplicationJSON{
				{ID: "h1", Status: "Online", Degraded: apiv4.NewOptNilBool(true), DegradedReason: apiv4.NewOptNilString("storage: not responding: /isard/groups")},
				{ID: "h2", Status: "Online", Degraded: apiv4.NewOptNilBool(true), DegradedReason: apiv4.NewOptNilString("timeout during start_domain")},
			},
			Metric: "isardvdi_isardvdi_api_hypervisor_degraded",
			Expected: `
# HELP isardvdi_isardvdi_api_hypervisor_degraded Whether the engine has marked an online hypervisor degraded, with the family of the reason
# TYPE isardvdi_isardvdi_api_hypervisor_degraded gauge
isardvdi_isardvdi_api_hypervisor_degraded{id="h1",reason="storage"} 1
isardvdi_isardvdi_api_hypervisor_degraded{id="h2",reason="libvirt"} 1
`,
		},
		"should export a not degraded online hypervisor with an empty reason": {
			Hypervisors: apiv4.StatsHypervisorsOKApplicationJSON{
				{ID: "h1", Status: "Online"},
			},
			Metric: "isardvdi_isardvdi_api_hypervisor_degraded",
			Expected: `
# HELP isardvdi_isardvdi_api_hypervisor_degraded Whether the engine has marked an online hypervisor degraded, with the family of the reason
# TYPE isardvdi_isardvdi_api_hypervisor_degraded gauge
isardvdi_isardvdi_api_hypervisor_degraded{id="h1",reason=""} 0
`,
		},
		"should not export the degraded state if the hypervisor is not online": {
			Hypervisors: apiv4.StatsHypervisorsOKApplicationJSON{
				{ID: "h1", Status: "Offline", Degraded: apiv4.NewOptNilBool(true), DegradedReason: apiv4.NewOptNilString("libvirt: check failed")},
				{ID: "h2", Status: "Online"},
			},
			Metric: "isardvdi_isardvdi_api_hypervisor_degraded",
			Expected: `
# HELP isardvdi_isardvdi_api_hypervisor_degraded Whether the engine has marked an online hypervisor degraded, with the family of the reason
# TYPE isardvdi_isardvdi_api_hypervisor_degraded gauge
isardvdi_isardvdi_api_hypervisor_degraded{id="h2",reason=""} 0
`,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx := t.Context()
			l := log.New("test", "debug")

			users := apiv4.StatsUsersOKApplicationJSON{}
			domainStatus := apiv4.StatsDomainsStatusResponse{
				Desktop:  apiv4.NewOptStatsDomainsStatusResponseDesktop(apiv4.StatsDomainsStatusResponseDesktop{"Started": 3}),
				Template: apiv4.NewOptStatsDomainsStatusResponseTemplate(apiv4.StatsDomainsStatusResponseTemplate{"Stopped": 2}),
			}
			desktops := apiv4.StatsDesktopsOKApplicationJSON{}
			categories := apiv4.StatsCategoriesResponse{}
			templates := apiv4.StatsTemplatesOKApplicationJSON{}
			hypervisors := tc.Hypervisors
			deployments := apiv4.StatsCategoriesDeploymentsResponse{}
			connected := tc.Connected

			cli := apiv4.NewMockInvoker(t)
			cli.On("StatsUsers", ctx).Return(&users, nil)
			cli.On("StatsDomainsStatus", ctx).Return(&domainStatus, nil)
			cli.On("StatsDesktops", ctx).Return(&desktops, nil)
			cli.On("StatsCategories", ctx).Return(&categories, nil)
			cli.On("StatsTemplates", ctx).Return(&templates, nil)
			cli.On("StatsHypervisors", ctx).Return(&hypervisors, nil)
			cli.On("StatsCategoriesDeployments", ctx).Return(&deployments, nil)
			cli.On("StatsConnectedUsers", ctx).Return(&connected, nil)

			a := NewIsardVDIAPI(ctx, l, cli)
			expected := strings.NewReader(tc.Expected)

			assert.NoError(testutil.CollectAndCompare(a, expected, tc.Metric))
		})
	}
}

func TestDegradedFamily(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Reason   string
		Expected string
	}{
		"should return storage if the reason is a storage one": {
			Reason:   "storage: probe failed: timed out",
			Expected: "storage",
		},
		"should return health if the reason is a health one": {
			Reason:   "health: no report for 45s",
			Expected: "health",
		},
		"should return libvirt if the reason is a libvirt one": {
			Reason:   "libvirt: check timed out after 30s",
			Expected: "libvirt",
		},
		"should return libvirt if the reason is a timeout during an operation": {
			Reason:   "timeout during list_domain_states",
			Expected: "libvirt",
		},
		"should return libvirt if the reason is a slow response": {
			Reason:   "slow_response",
			Expected: "libvirt",
		},
		"should return other if the reason has an unknown prefix": {
			Reason:   "something: with a colon in the text",
			Expected: "other",
		},
		"should return other if the reason has no prefix": {
			Reason:   "unknown",
			Expected: "other",
		},
		"should return other if the reason is empty": {
			Reason:   "",
			Expected: "other",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(tc.Expected, degradedFamily(tc.Reason))
		})
	}
}
