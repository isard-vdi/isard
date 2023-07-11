package log

import (
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
)

type OperationsV1HypervisorCapabilities struct {
	caps []operationsv1.HypervisorCapabilities
}

func NewOperationsV1HypervisorCapabilities(caps []operationsv1.HypervisorCapabilities) OperationsV1HypervisorCapabilities {
	return OperationsV1HypervisorCapabilities{caps}
}

func (o OperationsV1HypervisorCapabilities) MarshalZerologArray(a *zerolog.Array) {
	for _, c := range o.caps {
		a.Str(c.String())
	}
}

type OperationsV1ListHypervisorsResponse struct {
	rsp *operationsv1.ListHypervisorsResponse
}

func NewOperationsV1ListHypervisorsResponse(rsp *operationsv1.ListHypervisorsResponse) OperationsV1ListHypervisorsResponse {
	return OperationsV1ListHypervisorsResponse{rsp}
}

func (o OperationsV1ListHypervisorsResponse) MarshalZerologArray(a *zerolog.Array) {
	for _, h := range o.rsp.Hypervisors {
		a.Object(NewOperationsV1ListHypervisorsResponseHypervisor(h))
	}
}

type OperationsV1ListHypervisorsResponseHypervisor struct {
	hyp *operationsv1.ListHypervisorsResponseHypervisor
}

func NewOperationsV1ListHypervisorsResponseHypervisor(hyp *operationsv1.ListHypervisorsResponseHypervisor) OperationsV1ListHypervisorsResponseHypervisor {
	return OperationsV1ListHypervisorsResponseHypervisor{hyp}
}

func (o OperationsV1ListHypervisorsResponseHypervisor) MarshalZerologObject(e *zerolog.Event) {
	e.Str("id", o.hyp.Id).Str("state", o.hyp.State.String()).Int32("total_cpu", o.hyp.Cpu).Int32("total_ram", o.hyp.Ram).Array("capabilities", NewOperationsV1HypervisorCapabilities(o.hyp.Capabilities))
}
