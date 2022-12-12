package director_test

import (
	"context"
	"os"
	"testing"

	"gitlab.com/isard/isardvdi-cli/pkg/client"
	apiMock "gitlab.com/isard/isardvdi-cli/pkg/client/mock"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestRataNeedToScaleHypervisors(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                    []*model.Hypervisor
		RataMinCPU                int
		RataMinRAM                int
		ExpectedErr               string
		ExpectedCreateHypervisor  *operationsv1.CreateHypervisorRequest
		ExpectedDestroyHypervisor *operationsv1.DestroyHypervisorRequest
	}{
		"if there's enough RAM, it should return 0": {
			Hypers: []*model.Hypervisor{{
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 300,
					Used:  150,
					Free:  150,
				},
			}},
			RataMinRAM: 100,
		},
		"if there's not enough RAM, it should return the number of required hypervisors": {
			Hypers: []*model.Hypervisor{{
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}},
			RataMinRAM: 500,
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorRequest{
				MinRam: 400,
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)
			rata := director.NewRata(cfg.DirectorRata{
				MinCPU: tc.RataMinCPU,
				MinRAM: tc.RataMinRAM,
			}, &log, nil)

			create, destroy, err := rata.NeedToScaleHypervisors(context.Background(), tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedCreateHypervisor, create)
			assert.Equal(tc.ExpectedDestroyHypervisor, destroy)
		})
	}
}

func TestRataExtraOperations(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI  func(*apiMock.Client)
		Hypers      []*model.Hypervisor
		HyperMinCPU int
		HyperMinRAM int
		ExpectedErr string
	}{
		"if there are enough resources, it shouldn't do anything": {
			PrepareAPI: func(c *apiMock.Client) {},
			Hypers: []*model.Hypervisor{{
				ID:     "first",
				Status: client.HypervisorStatusOffline,
				RAM: model.ResourceLoad{
					Free: 10,
				},
			}, {
				ID:     "second",
				Status: client.HypervisorStatusOnline,
				RAM: model.ResourceLoad{
					Free: 60,
				},
			}},
			HyperMinRAM: 50,
		},
		"if there's not enough RAM, it should set the hypervisor to only forced": {
			PrepareAPI: func(c *apiMock.Client) {
				c.Mock.On("AdminHypervisorOnlyForced", mock.AnythingOfType("*context.emptyCtx"), "second", true).Return(nil)
			},
			Hypers: []*model.Hypervisor{{
				ID:     "first",
				Status: client.HypervisorStatusOffline,
				RAM: model.ResourceLoad{
					Free: 10,
				},
			}, {
				ID:     "second",
				Status: client.HypervisorStatusOnline,
				RAM: model.ResourceLoad{
					Free: 30,
				},
			}},
			HyperMinRAM: 50,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)
			api := &apiMock.Client{}

			tc.PrepareAPI(api)

			rata := director.NewRata(cfg.DirectorRata{
				HyperMinCPU: tc.HyperMinCPU,
				HyperMinRAM: tc.HyperMinRAM,
			}, &log, api)

			err := rata.ExtraOperations(context.Background(), tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}
