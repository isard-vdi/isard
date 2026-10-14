package orchestrator

import (
	"context"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

// sharedStorageStalled reports the engine's stall condition; an unreadable one does not stop scaling.
func (o *Orchestrator) sharedStorageStalled(ctx context.Context) bool {
	res, err := o.apiCli.AdminSharedStorageStall(ctx)
	if err != nil {
		o.log.Error().Err(err).Msg("get the shared storage stall condition")
		return false
	}

	stall, ok := res.(*apiv4.SharedStorageStallResponse)
	if !ok {
		o.log.Error().Err(ogenclient.AsAPIError(res)).Msg("get the shared storage stall condition")
		return false
	}

	if !stall.Active.Or(false) {
		return false
	}

	o.log.Warn().Strs("hypervisors", stall.Hypervisors).Strs("mounts", stall.Mounts).Msg("shared storage stall, skipping hypervisor scaling")
	return true
}
