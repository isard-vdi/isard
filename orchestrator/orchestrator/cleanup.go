package orchestrator

import (
	"context"
	"fmt"

	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

// cleanup removes "zombie" hypervisors (hypervisors that no longer exist in the operations service, but are still in the API but are not online)
func (o *Orchestrator) cleanup(ctx context.Context, api []*sdk.OrchestratorHypervisor, operations []*operationsv1.ListHypervisorsResponseHypervisor) error {
	for _, h := range api {
		found := false
		for _, oH := range operations {
			if h.ID == oH.GetId() {
				found = true
			}
		}

		// Check if the hypervisor is a zombie
		if !found && h.OrchestratorManaged && h.Status != sdk.HypervisorStatusOnline {
			// If it's a zombie, add it to the dead row!
			if err := o.apiCli.HypervisorDelete(ctx, h.ID); err != nil {
				return fmt.Errorf("kill zombie hypervisor '%s': %w", h.ID, err)
			}
		}
	}

	return nil
}
