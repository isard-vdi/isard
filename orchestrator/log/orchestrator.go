package log

import (
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
)

type ModelHypervisor struct {
	h *client.OrchestratorHypervisor
}

func NewModelHypervisor(h *client.OrchestratorHypervisor) ModelHypervisor {
	return ModelHypervisor{h}
}

func (m ModelHypervisor) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", m.h.ID).Str("status", string(m.h.Status)).Bool("only_forced", m.h.OnlyForced).Bool("buffering", m.h.Buffering).Time("destroy_time", m.h.DestroyTime).Object("cpu", NewModelResourceLoad(m.h.CPU)).Object("ram", NewModelResourceLoad(m.h.RAM))
}

type ModelResourceLoad struct {
	r client.OrchestratorResourceLoad
}

func NewModelResourceLoad(r client.OrchestratorResourceLoad) ModelResourceLoad {
	return ModelResourceLoad{r}
}

func (r ModelResourceLoad) MarshalZerologObject(e *zerolog.Event) {
	e.Int("total", r.r.Total).Int("used", r.r.Used).Int("free", r.r.Free)
}

type ModelHypervisors struct {
	hyps []*client.OrchestratorHypervisor
}

func NewModelHypervisors(hyps []*client.OrchestratorHypervisor) ModelHypervisors {
	return ModelHypervisors{hyps}
}

func (m ModelHypervisors) MarshalZerologArray(a *zerolog.Array) {
	for _, h := range m.hyps {
		a.Object(NewModelHypervisor(h))
	}
}
