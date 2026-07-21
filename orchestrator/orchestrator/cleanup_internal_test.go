package orchestrator

import (
	"errors"
	"testing"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestCleanup(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI            func(*apiv4.MockInvoker)
		APIHypervisors        []*apiv4.OrchestratorHypervisor
		OperationsHypervisors []*operationsv1.ListHypervisorsResponseHypervisor
		ExpectedErr           string
	}{
		"should kill the zombie hypervisor correctly": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminHypervisorDelete", mock.AnythingOfType("*context.cancelCtx"), apiv4.AdminHypervisorDeleteParams{HyperID: "zombie"}).Return(&apiv4.AdminHypervisorDeleteNoContent{}, nil)
			},
			APIHypervisors: []*apiv4.OrchestratorHypervisor{{
				ID:                  "zombie",
				OrchestratorManaged: true,
				Status:              apiv4.HypervisorStatusOffline,
			}, {
				ID:                  "unmanaged-zombie",
				OrchestratorManaged: false,
				Status:              apiv4.HypervisorStatusOffline,
			}, {
				ID:                  "just offline",
				OrchestratorManaged: true,
				Status:              apiv4.HypervisorStatusOffline,
			}, {
				ID:                  "online",
				OrchestratorManaged: true,
				Status:              apiv4.HypervisorStatusOnline,
			}},
			OperationsHypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id: "just offline",
			}, {
				Id: "hyper available",
			}},
		},
		"should return an error if there's an error deleting the hypervisor": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminHypervisorDelete", mock.AnythingOfType("*context.cancelCtx"), apiv4.AdminHypervisorDeleteParams{HyperID: "zombie"}).Return(nil, errors.New("oh no :("))
			},
			APIHypervisors: []*apiv4.OrchestratorHypervisor{{
				ID:                  "zombie",
				OrchestratorManaged: true,
				Status:              apiv4.HypervisorStatusOffline,
			}},
			OperationsHypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{},
			ExpectedErr:           "kill zombie hypervisor 'zombie': oh no :(",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			api := apiv4.NewMockInvoker(t)
			o := &Orchestrator{
				apiCli: api,
			}

			tc.PrepareAPI(api)

			err := o.cleanup(t.Context(), tc.APIHypervisors, tc.OperationsHypervisors)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}
