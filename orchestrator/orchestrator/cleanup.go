package orchestrator

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

// cleanup removes "zombie" hypervisors (hypervisors that no longer exist in the operations service, but are still in the API but are not online)
func (o *Orchestrator) cleanup(ctx context.Context, api []*model.Hypervisor, operations []*operationsv1.ListHypervisorsResponseHypervisor) error {
	for _, h := range api {
		found := false
		for _, oH := range operations {
			if h.ID == oH.GetId() {
				found = true
			}
		}

		// Check if the hypervisor is a zombie
		if !found && h.OrchestratorManaged.Or(false) && h.Status != model.HypervisorStatusOnline {
			// If it's a zombie, delete it!
			if err := o.adminHypervisorDelete(ctx, h.ID); err != nil {
				return fmt.Errorf("kill zombie hypervisor '%s': %w", h.ID, err)
			}
		}
	}

	return nil
}

func (o *Orchestrator) adminHypervisorDelete(ctx context.Context, id string) error {
	res, err := o.apiCli.AdminHypervisorDelete(ctx, apiv4.AdminHypervisorDeleteParams{
		HyperID: id,
	})
	if err != nil {
		return fmt.Errorf("delete hypervisor %q: %w", id, err)
	}

	if _, ok := res.(*apiv4.EmptyResponse); ok {
		return nil
	}

	return ogenclient.AsAPIError(res)
}
