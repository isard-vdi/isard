package orchestrator

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model/testhelper"
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
		APIHypervisors        []*model.Hypervisor
		OperationsHypervisors []*operationsv1.ListHypervisorsResponseHypervisor
		ExpectedErr           string
	}{
		"should kill the zombie hypervisor correctly": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminHypervisorDelete", mock.AnythingOfType("*context.cancelCtx"), apiv4.AdminHypervisorDeleteParams{HyperID: "zombie"}).Return(&apiv4.AdminHypervisorDeleteNoContent{}, nil)
			},
			APIHypervisors: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("zombie"),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithStatus(model.HypervisorStatusOffline),
				),
				testhelper.Hypervisor(
					testhelper.WithID("unmanaged-zombie"),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithStatus(model.HypervisorStatusOffline),
				),
				testhelper.Hypervisor(
					testhelper.WithID("just offline"),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithStatus(model.HypervisorStatusOffline),
				),
				testhelper.Hypervisor(
					testhelper.WithID("online"),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithStatus(model.HypervisorStatusOnline),
				),
			},
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
			APIHypervisors: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("zombie"),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithStatus(model.HypervisorStatusOffline),
				),
			},
			OperationsHypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{},
			ExpectedErr:           "kill zombie hypervisor 'zombie': delete hypervisor \"zombie\": oh no :(",
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
