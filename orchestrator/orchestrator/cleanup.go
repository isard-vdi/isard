package orchestrator

import (
	"context"
	"fmt"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

// cleanup removes "zombie" hypervisors (hypervisors that no longer exist in the operations service, but are still in the API but are not online)
func (o *Orchestrator) cleanup(ctx context.Context, api []*apiv4.OrchestratorHypervisor, operations []*operationsv1.ListHypervisorsResponseHypervisor) error {
	for _, h := range api {
		found := false
		for _, oH := range operations {
			if h.ID == oH.GetId() {
				found = true
			}
		}

		// Check if the hypervisor is a zombie
		if !found && h.OrchestratorManaged && h.Status != apiv4.HypervisorStatusOnline {
			// If it's a zombie, add it to the dead row!
			res, err := o.apiCli.AdminHypervisorDelete(ctx, apiv4.AdminHypervisorDeleteParams{HyperID: h.ID})
			if err != nil {
				return fmt.Errorf("kill zombie hypervisor '%s': %w", h.ID, err)
			}
			if _, ok := res.(*apiv4.AdminHypervisorDeleteNoContent); !ok {
				return fmt.Errorf("kill zombie hypervisor '%s': %w", h.ID, ogenclient.AsAPIError(res))
			}
		}
	}

	return nil
}
