package orchestrator

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
	apiMock "gitlab.com/isard/isardvdi-cli/pkg/client/mock"
)

func TestOrchestratorOpenBufferingHypervisor(t *testing.T) {
	assert := assert.New(t)

	api := &apiMock.Client{}
	o := &Orchestrator{
		apiCli: api,
	}

	cases := map[string]struct {
		PrepareAPI  func(*apiMock.Client)
		ExpectedErr string
	}{
		// "should work as expected": {
		// 	PrepareAPI: func(c *apiMock.Client) {
		// 		f := false
		// 		t := true
		// 		id := "theHyper"

		// 		c.On("HypervisorList", mock.AnythingOfType("*context.emptyCtx")).Return([]*client.Hypervisor{{
		// 			Buffering: &f,
		// 		}, {
		// 			ID:         &id,
		// 			Buffering:  &t,
		// 			OnlyForced: &t,
		// 		}}, nil)

		// 		c.On("AdminHypervisorOnlyForced", mock.AnythingOfType("*context.emptyCtx"), "theHyper", false).Return(nil)
		// 	},
		// },
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiMock.Client) {
				f := false
				t := true

				c.On("HypervisorList", mock.AnythingOfType("*context.emptyCtx")).Return([]*client.Hypervisor{{
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

	api := &apiMock.Client{}
	o := &Orchestrator{
		apiCli: api,
	}

	cases := map[string]struct {
		PrepareAPI  func(*apiMock.Client)
		ExpectedErr string
	}{
		// "should work as expected": {
		// 	PrepareAPI: func(c *apiMock.Client) {
		// 		f := false
		// 		t := true
		// 		id := "theHyper"

		// 		c.On("HypervisorList", mock.AnythingOfType("*context.emptyCtx")).Return([]*client.Hypervisor{{
		// 			Buffering: &f,
		// 		}, {
		// 			ID:         &id,
		// 			Buffering:  &t,
		// 			OnlyForced: &f,
		// 		}}, nil)

		// 		c.On("AdminHypervisorOnlyForced", mock.AnythingOfType("*context.emptyCtx"), "theHyper", true).Return(nil)
		// 	},
		// },
		"should not do anything if there are no operations to do": {
			PrepareAPI: func(c *apiMock.Client) {
				f := false
				t := true

				c.On("HypervisorList", mock.AnythingOfType("*context.emptyCtx")).Return([]*client.Hypervisor{{
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
