package director_test

import (
	"context"
	"os"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi-cli/pkg/client"
	apiMock "gitlab.com/isard/isardvdi-cli/pkg/client/mock"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestRataNeedToScaleHypervisors(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		AvailHypers               []*operationsv1.ListHypervisorsResponseHypervisor
		Hypers                    []*model.Hypervisor
		RataMinCPU                int
		RataMinRAM                int
		PrepareDB                 func(mock *r.Mock)
		ExpectedErr               string
		ExpectedCreateHypervisor  *operationsv1.CreateHypervisorRequest
		ExpectedDestroyHypervisor *operationsv1.DestroyHypervisorRequest
	}{
		"if there's enough RAM, it should return 0": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
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
		"if there's not enough RAM, it should return the ID of the hypervisor that needs to be created": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:    "testing",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   5000,
			}, {
				Id:    "HUGE HYPERVISOR",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   99999999,
			}, {
				Id:    "already",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   300,
			}},
			Hypers: []*model.Hypervisor{{
				ID:         "already",
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
				Id: "testing",
			},
		},
		"if there's too much free RAM, it should add the biggest hypervisor that it can to the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{{
				ID:         "1",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 500,
					Used:  100,
					Free:  400,
				},
			}, {
				ID:         "2",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: true,
				RAM: model.ResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}, {
				ID:         "3",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 300,
					Used:  100,
					Free:  400,
				},
			}},
			RataMinRAM: 300,
			PrepareDB: func(mock *r.Mock) {
				mock.On(r.Table("hypervisors").Get("2").Update(map[string]interface{}{
					"destroy_time": r.MockAnything(),
					"only_forced":  true,
				}))
			},
		},
		"if there's not enough RAM but there are hypervisors on the dead row, it should remove those from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:  "testing",
				Ram: 5000,
			}, {
				Id:  "HUGE HYPERVISOR",
				Ram: 99999999,
			}},
			Hypers: []*model.Hypervisor{{
				ID:         "existing-1",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}, {
				ID:          "existing-2",
				Status:      client.HypervisorStatusOnline,
				OnlyForced:  false,
				DestroyTime: time.Now().Add(time.Hour),
				RAM: model.ResourceLoad{
					Total: 3000,
					Used:  2000,
					Free:  1000,
				},
			}},
			RataMinRAM: 500,
			PrepareDB: func(mock *r.Mock) {
				mock.On(r.Table("hypervisors").Get("existing-2").Update(map[string]interface{}{
					"destroy_time": nil,
				}))
			},
		},
		"if there's not enough RAM and there are multiple hypervisors on the dead row, it should remove the smallest hypervisor from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:  "testing",
				Ram: 5000,
			}, {
				Id:  "HUGE HYPERVISOR",
				Ram: 99999999,
			}},
			Hypers: []*model.Hypervisor{{
				ID:         "existing-1",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}, {
				ID:          "existing-2",
				Status:      client.HypervisorStatusOnline,
				OnlyForced:  false,
				DestroyTime: time.Now().Add(time.Hour),
				RAM: model.ResourceLoad{
					Total: 3000,
					Used:  2000,
					Free:  1000,
				},
			}, {
				ID:          "existing-3",
				Status:      client.HypervisorStatusOnline,
				OnlyForced:  false,
				DestroyTime: time.Now().Add(time.Hour),
				RAM: model.ResourceLoad{
					Total: 1000,
					Used:  300,
					Free:  700,
				},
			}},
			RataMinRAM: 500,
			PrepareDB: func(mock *r.Mock) {
				mock.On(r.Table("hypervisors").Get("existing-3").Update(map[string]interface{}{
					"destroy_time": nil,
				}))
			},
		},
		"if there's an hypervisor that's been too much time on the dead row, KILL THEM!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{{
				ID:         "1",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 500,
					Used:  400,
					Free:  100,
				},
			}, {
				ID:          "2",
				Status:      client.HypervisorStatusOnline,
				DestroyTime: time.Now().Add(-2 * director.DeadRowDuration),
				OnlyForced:  true,
				RAM: model.ResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}, {
				ID:         "3",
				Status:     client.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: model.ResourceLoad{
					Total: 500,
					Used:  250,
					Free:  250,
				},
			}},
			RataMinRAM: 300,
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorRequest{
				Id: "2",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			db := r.NewMock()
			if tc.PrepareDB != nil {
				tc.PrepareDB(db)
			}

			rata := director.NewRata(cfg.DirectorRata{
				MinCPU: tc.RataMinCPU,
				MinRAM: tc.RataMinRAM,
			}, false, &log, nil, db)

			create, destroy, err := rata.NeedToScaleHypervisors(context.Background(), tc.AvailHypers, tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedCreateHypervisor, create)
			assert.Equal(tc.ExpectedDestroyHypervisor, destroy)

			db.AssertExpectations(t)
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
		HyperMaxRAM int
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
		"if there's too much free RAM, it should remove the hypervisor from only forced": {
			PrepareAPI: func(c *apiMock.Client) {
				c.Mock.On("AdminHypervisorOnlyForced", mock.AnythingOfType("*context.emptyCtx"), "second", false).Return(nil)
			},
			Hypers: []*model.Hypervisor{{
				ID:     "first",
				Status: client.HypervisorStatusOffline,
				RAM: model.ResourceLoad{
					Free: 10,
				},
			}, {
				ID:         "second",
				OnlyForced: true,
				Status:     client.HypervisorStatusOnline,
				RAM: model.ResourceLoad{
					Free: 200,
				},
			}},
			HyperMinRAM: 50,
			HyperMaxRAM: 150,
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
				HyperMaxRAM: tc.HyperMaxRAM,
			}, false, &log, api, nil)

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
