package orchestrator

import (
	"context"
	"testing"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestOrchestratorOpenBufferingHypervisor(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI  func(*apiv4.MockInvoker)
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					BufferingHyper: false,
				}, {
					ID:             "theHyper",
					BufferingHyper: true,
					OnlyForced:     true,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)

				c.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("context.backgroundCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: false}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "theHyper"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
		},
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					BufferingHyper: false,
				}, {
					BufferingHyper: true,
					OnlyForced:     false,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			api := apiv4.NewMockInvoker(t)
			o := &Orchestrator{
				apiCli: api,
			}

			tc.PrepareAPI(api)

			err := o.openBufferingHypervisor(context.Background())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}

func TestOrchestratorCloseBufferingHypervisor(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI  func(*apiv4.MockInvoker)
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					BufferingHyper: false,
				}, {
					ID:             "theHyper",
					BufferingHyper: true,
					OnlyForced:     false,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)

				c.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("context.backgroundCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: true}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "theHyper"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
		},
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					BufferingHyper: false,
				}, {
					BufferingHyper: true,
					OnlyForced:     true,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			api := apiv4.NewMockInvoker(t)
			o := &Orchestrator{
				apiCli: api,
			}

			tc.PrepareAPI(api)

			err := o.closeBufferingHypervisor(context.Background())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}
