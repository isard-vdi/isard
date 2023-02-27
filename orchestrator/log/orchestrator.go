package log

import (
	"gitlab.com/isard/isardvdi/orchestrator/model"

	"github.com/rs/zerolog"
)

type ModelHypervisor struct {
	h *model.Hypervisor
}

func NewModelHypervisor(h *model.Hypervisor) ModelHypervisor {
	return ModelHypervisor{h}
}

func (m ModelHypervisor) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", m.h.ID).Str("status", string(m.h.Status)).Bool("only_forced", m.h.OnlyForced).Bool("buffering", m.h.Buffering).Time("destroy_time", m.h.DestroyTime).Object("cpu", NewModelResourceLoad(m.h.CPU)).Object("ram", NewModelResourceLoad(m.h.RAM))
}

type ModelResourceLoad struct {
	r model.ResourceLoad
}

func NewModelResourceLoad(r model.ResourceLoad) ModelResourceLoad {
	return ModelResourceLoad{r}
}

func (r ModelResourceLoad) MarshalZerologObject(e *zerolog.Event) {
	e.Int("total", r.r.Total).Int("used", r.r.Used).Int("free", r.r.Free)
}

type ModelHypervisors struct {
	hyps []*model.Hypervisor
}

func NewModelHypervisors(hyps []*model.Hypervisor) ModelHypervisors {
	return ModelHypervisors{hyps}
}

func (m ModelHypervisors) MarshalZerologArray(a *zerolog.Array) {
	for _, h := range m.hyps {
		a.Object(NewModelHypervisor(h))
	}
}
