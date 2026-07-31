package log

import (
	"time"

	"github.com/rs/zerolog"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
)

type ModelHypervisor struct {
	h *apiv4.OrchestratorHypervisor
}

func NewModelHypervisor(h *apiv4.OrchestratorHypervisor) ModelHypervisor {
	return ModelHypervisor{h}
}

func (m ModelHypervisor) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", m.h.ID).
		Str("status", string(m.h.Status)).
		Bool("only_forced", m.h.OnlyForced).
		Bool("buffering", m.h.BufferingHyper).
		Time("destroy_time", m.h.DestroyTime.Or(time.Time{})).
		Time("bookings_end_time", m.h.BookingsEndTime.Or(time.Time{})).
		Bool("orchestrator_managed", m.h.OrchestratorManaged).
		Bool("gpu_only", m.h.GpuOnly).
		Int("desktops_started", m.h.DesktopsStarted).
		Int("min_free_mem_gb", m.h.MinFreeMemGB).
		Object("cpu", NewModelResourceLoad(m.h.CPU)).
		Object("ram", NewModelResourceLoad(m.h.RAM)).
		Array("gpus", NewModelGPUs(m.h.Gpus))
}

type ModelResourceLoad struct {
	r apiv4.OrchestratorResourceLoad
}

func NewModelResourceLoad(r apiv4.OrchestratorResourceLoad) ModelResourceLoad {
	return ModelResourceLoad{r}
}

func (r ModelResourceLoad) MarshalZerologObject(e *zerolog.Event) {
	e.Int("total", r.r.Total).Int("used", r.r.Used).Int("free", r.r.Free)
}

type ModelGPUs struct {
	gpus []apiv4.OrchestratorHypervisorGPU
}

func NewModelGPUs(gpus []apiv4.OrchestratorHypervisorGPU) ModelGPUs {
	return ModelGPUs{gpus}
}

func (g ModelGPUs) MarshalZerologArray(a *zerolog.Array) {
	for _, g := range g.gpus {
		a.Object(NewModelGPU(&g))
	}
}

type ModelGPU struct {
	g *apiv4.OrchestratorHypervisorGPU
}

func NewModelGPU(g *apiv4.OrchestratorHypervisorGPU) ModelGPU {
	return ModelGPU{g}
}

func (g ModelGPU) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", g.g.ID).
		Str("brand", g.g.Brand).
		Str("model", g.g.Model).
		Str("profile", g.g.Profile).
		Int("total_units", g.g.TotalUnits).
		Int("free_units", g.g.FreeUnits).
		Int("used_units", g.g.UsedUnits)
}

type ModelHypervisors struct {
	hyps []*apiv4.OrchestratorHypervisor
}

func NewModelHypervisors(hyps []*apiv4.OrchestratorHypervisor) ModelHypervisors {
	return ModelHypervisors{hyps}
}

func (m ModelHypervisors) MarshalZerologArray(a *zerolog.Array) {
	for _, h := range m.hyps {
		a.Object(NewModelHypervisor(h))
	}
}

type ModelBooking struct {
	b *apiv4.GpuForecastProfile
}

func NewModelBooking(b *apiv4.GpuForecastProfile) ModelBooking {
	return ModelBooking{b}
}

func (b ModelBooking) MarshalZerologObject(e *zerolog.Event) {
	e.Str("brand", b.b.Brand).
		Str("model", b.b.Model).
		Str("profile", b.b.Profile).
		Dict("now", zerolog.Dict().
			Time("time", b.b.Now.Date).
			Int("units", b.b.Now.Units),
		).
		Dict("create", zerolog.Dict().
			Time("time", b.b.ToCreate.Date).
			Int("units", b.b.ToCreate.Units),
		).
		Dict("destroy", zerolog.Dict().
			Time("time", b.b.ToDestroy.Date).
			Int("units", b.b.ToDestroy.Units),
		)

}

type ModelBookings struct {
	b []apiv4.GpuForecastProfile
}

func NewModelBookings(b []apiv4.GpuForecastProfile) ModelBookings {
	return ModelBookings{b}
}

func (b ModelBookings) MarshalZerologArray(a *zerolog.Array) {
	for _, b := range b.b {
		a.Object(NewModelBooking(&b))
	}
}
