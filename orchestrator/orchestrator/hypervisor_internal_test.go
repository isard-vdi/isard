package orchestrator

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

func TestOrchestratorOpenBufferingHypervisor(t *testing.T) {
	assert := assert.New(t)

	api := sdk.NewMockSdk(t)
	o := &Orchestrator{
		apiCli: api,
	}

	cases := map[string]struct {
		PrepareAPI  func(*sdk.MockSdk)
		ExpectedErr string
	}{
		// "should work as expected": {
		// 	PrepareAPI: func(c *sdk.MockSdk) {
		// 		f := false
		// 		t := true
		// 		id := "theHyper"

		// 		c.On("HypervisorList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.Hypervisor{{
		// 			Buffering: &f,
		// 		}, {
		// 			ID:         &id,
		// 			Buffering:  &t,
		// 			OnlyForced: &t,
		// 		}}, nil)

		// 		c.On("AdminHypervisorOnlyForced", mock.AnythingOfType("context.backgroundCtx"), "theHyper", false).Return(nil)
		// 	},
		// },
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *sdk.MockSdk) {
				f := false
				t := true

				c.On("HypervisorList", mock.AnythingOfType("context.backgroundCtx")).Return([]*sdk.Hypervisor{{
					Buffering: &f,
				}, {
					Buffering:  &t,
					OnlyForced: &f,
				}}, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
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

	api := sdk.NewMockSdk(t)
	o := &Orchestrator{
		apiCli: api,
	}

	cases := map[string]struct {
		PrepareAPI  func(*sdk.MockSdk)
		ExpectedErr string
	}{
		// "should work as expected": {
		// 	PrepareAPI: func(c *sdk.MockSdk) {
		// 		f := false
		// 		t := true
		// 		id := "theHyper"

		// 		c.On("HypervisorList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.Hypervisor{{
		// 			Buffering: &f,
		// 		}, {
		// 			ID:         &id,
		// 			Buffering:  &t,
		// 			OnlyForced: &f,
		// 		}}, nil)

		// 		c.On("AdminHypervisorOnlyForced", mock.AnythingOfType("context.backgroundCtx"), "theHyper", true).Return(nil)
		// 	},
		// },
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *sdk.MockSdk) {
				f := false
				t := true

				c.On("HypervisorList", mock.AnythingOfType("context.backgroundCtx")).Return([]*sdk.Hypervisor{{
					Buffering: &f,
				}, {
					Buffering:  &t,
					OnlyForced: &t,
				}}, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
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
