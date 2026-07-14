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
					ID:             "non-buffering",
					BufferingHyper: false,
				}, {
					ID:             "theHyper",
					BufferingHyper: true,
					OnlyForced:     true,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)

				c.On("AdminTableUpdate", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"theHyper"` && string(req["only_forced"]) == "false"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
			},
		},
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					ID:             "non-buffering",
					BufferingHyper: false,
				}, {
					ID:             "buffering-already-open",
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
					ID:             "non-buffering",
					BufferingHyper: false,
				}, {
					ID:             "theHyper",
					BufferingHyper: true,
					OnlyForced:     false,
				}})
				c.On("AdminHypervisorsList", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminHypervisorsListParams{}).Return(&list, nil)

				c.On("AdminTableUpdate", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"theHyper"` && string(req["only_forced"]) == "true"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
			},
		},
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				list := apiv4.AdminHypervisorsListOKApplicationJSON([]apiv4.AdminHypervisor{{
					ID:             "non-buffering",
					BufferingHyper: false,
				}, {
					ID:             "buffering-already-closed",
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
