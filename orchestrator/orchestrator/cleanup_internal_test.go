package orchestrator

import (
	"context"
	"errors"
	"testing"

	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/sdk"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestCleanup(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI            func(*sdk.MockSdk)
		APIHypervisors        []*sdk.OrchestratorHypervisor
		OperationsHypervisors []*operationsv1.ListHypervisorsResponseHypervisor
		ExpectedErr           string
	}{
		"should kill the zombie hypervisor correctly": {
			PrepareAPI: func(c *sdk.MockSdk) {
				c.On("HypervisorDelete", mock.AnythingOfType("context.backgroundCtx"), "zombie").Return(nil)
			},
			APIHypervisors: []*sdk.OrchestratorHypervisor{{
				ID:                  "zombie",
				OrchestratorManaged: true,
				Status:              sdk.HypervisorStatusOffline,
			}, {
				ID:                  "unmanaged-zombie",
				OrchestratorManaged: false,
				Status:              sdk.HypervisorStatusOffline,
			}, {
				ID:                  "just offline",
				OrchestratorManaged: true,
				Status:              sdk.HypervisorStatusOffline,
			}, {
				ID:                  "online",
				OrchestratorManaged: true,
				Status:              sdk.HypervisorStatusOnline,
			}},
			OperationsHypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id: "just offline",
			}, {
				Id: "hyper available",
			}},
		},
		"should return an error if there's an error deleting the hypervisor": {
			PrepareAPI: func(c *sdk.MockSdk) {
				c.On("HypervisorDelete", mock.AnythingOfType("context.backgroundCtx"), "zombie").Return(errors.New("oh no :("))
			},
			APIHypervisors: []*sdk.OrchestratorHypervisor{{
				ID:                  "zombie",
				OrchestratorManaged: true,
				Status:              sdk.HypervisorStatusOffline,
			}},
			OperationsHypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{},
			ExpectedErr:           "kill zombie hypervisor 'zombie': oh no :(",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			api := sdk.NewMockSdk(t)
			o := &Orchestrator{
				apiCli: api,
			}

			tc.PrepareAPI(api)

			err := o.cleanup(context.Background(), tc.APIHypervisors, tc.OperationsHypervisors)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}
