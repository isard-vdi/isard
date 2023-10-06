package log

import (
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
)

type ModelHypervisor struct {
	h *isardvdi.OrchestratorHypervisor
}

func NewModelHypervisor(h *isardvdi.OrchestratorHypervisor) ModelHypervisor {
	return ModelHypervisor{h}
}

func (m ModelHypervisor) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", m.h.ID).
		Str("status", string(m.h.Status)).
		Bool("only_forced", m.h.OnlyForced).
		Bool("buffering", m.h.Buffering).
		Time("destroy_time", m.h.DestroyTime).
		Time("bookings_end_time", m.h.BookingsEndTime).
		Bool("orchestrator_managed", m.h.OrchestratorManaged).
		Bool("gpu_only", m.h.GPUOnly).
		Int("desktops_started", m.h.DesktopsStarted).
		Int("min_free_mem_gb", m.h.MinFreeMemGB).
		Object("cpu", NewModelResourceLoad(m.h.CPU)).
		Object("ram", NewModelResourceLoad(m.h.RAM)).
		Array("gpus", NewModelGPUs(m.h.GPUs))
}

type ModelResourceLoad struct {
	r isardvdi.OrchestratorResourceLoad
}

func NewModelResourceLoad(r isardvdi.OrchestratorResourceLoad) ModelResourceLoad {
	return ModelResourceLoad{r}
}

func (r ModelResourceLoad) MarshalZerologObject(e *zerolog.Event) {
	e.Int("total", r.r.Total).Int("used", r.r.Used).Int("free", r.r.Free)
}

type ModelGPUs struct {
	gpus []*isardvdi.OrchestratorHypervisorGPU
}

func NewModelGPUs(gpus []*isardvdi.OrchestratorHypervisorGPU) ModelGPUs {
	return ModelGPUs{gpus}
}

func (g ModelGPUs) MarshalZerologArray(a *zerolog.Array) {
	for _, g := range g.gpus {
		a.Object(NewModelGPU(g))
	}
}

type ModelGPU struct {
	g *isardvdi.OrchestratorHypervisorGPU
}

func NewModelGPU(g *isardvdi.OrchestratorHypervisorGPU) ModelGPU {
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
	hyps []*isardvdi.OrchestratorHypervisor
}

func NewModelHypervisors(hyps []*isardvdi.OrchestratorHypervisor) ModelHypervisors {
	return ModelHypervisors{hyps}
}

func (m ModelHypervisors) MarshalZerologArray(a *zerolog.Array) {
	for _, h := range m.hyps {
		a.Object(NewModelHypervisor(h))
	}
}

type ModelBooking struct {
	b *isardvdi.OrchestratorGPUBooking
}

func NewModelBooking(b *isardvdi.OrchestratorGPUBooking) ModelBooking {
	return ModelBooking{b}
}

func (b ModelBooking) MarshalZerologObject(e *zerolog.Event) {
	e.Str("brand", b.b.Brand).
		Str("model", b.b.Model).
		Str("profile", b.b.Profile).
		Dict("now", zerolog.Dict().
			Time("time", b.b.Now.Time).
			Int("units", b.b.Now.Units),
		).
		Dict("create", zerolog.Dict().
			Time("time", b.b.Create.Time).
			Int("units", b.b.Create.Units),
		).
		Dict("destroy", zerolog.Dict().
			Time("time", b.b.Destroy.Time).
			Int("units", b.b.Destroy.Units),
		)

}

type ModelBookings struct {
	b []*isardvdi.OrchestratorGPUBooking
}

func NewModelBookings(b []*isardvdi.OrchestratorGPUBooking) ModelBookings {
	return ModelBookings{b}
}

func (b ModelBookings) MarshalZerologArray(a *zerolog.Array) {
	for _, b := range b.b {
		a.Object(NewModelBooking(b))
	}
}
