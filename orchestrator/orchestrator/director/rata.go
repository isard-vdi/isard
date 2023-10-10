package director

import (
	"context"
	"fmt"
	"math"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
)

const (
	DirectorTypeRata = "rata"
	// 3,5 hours of dead row
	DeadRowDuration = 3*time.Hour + time.Hour/2
)

// Rata is a director that has some minimum values required.
// It waits until there are less values than the minimum, then it takes action
type Rata struct {
	cfg    cfg.DirectorRata
	dryRun bool

	apiCli isardvdi.Interface

	log *zerolog.Logger
}

func NewRata(cfg cfg.DirectorRata, dryRun bool, log *zerolog.Logger, apiCli isardvdi.Interface) *Rata {
	return &Rata{
		cfg:    cfg,
		dryRun: dryRun,
		apiCli: apiCli,

		log: log,
	}
}

func (r *Rata) String() string {
	return DirectorTypeRata
}

// minCPU is the minimum CPU number that need to be free in the pool. If it's zero, it's not going to use it
func (r *Rata) minCPU() int {
	if r.cfg.MinCPUHourly == nil {
		return r.cfg.MinCPU
	}

	return getCurrentHourlyLimit(r.cfg.MinCPUHourly, time.Now())
}

// minRAM is the minimum MB of RAM that need to be free in the pool. If it's zero, it's not going to use it
func (r *Rata) minRAM(hypers []*isardvdi.OrchestratorHypervisor) int {
	if r.cfg.MinRAMHourly != nil {
		return getCurrentHourlyLimit(r.cfg.MinRAMHourly, time.Now())
	}

	if r.cfg.MinRAM != 0 {
		return r.cfg.MinRAM
	}

	if r.cfg.MinRAMLimitPercent != 0 {
		margin := 0
		if r.cfg.MinRAMLimitMarginHourly != nil {
			margin = getCurrentHourlyLimit(r.cfg.MinRAMLimitMarginHourly, time.Now())
		} else {
			margin = r.cfg.MinRAMLimitMargin
		}

		minRAM := 0
		for _, h := range hypers {
			minRAM += (h.MinFreeMemGB * 1024) // we want it as MB, not GB
		}

		// Apply the limit percentage
		minRAM = int(math.Round((float64(r.cfg.MinRAMLimitPercent) / 100.0) * float64(minRAM)))
		// Sum the extra margin
		minRAM += margin

		return minRAM
	}

	return 0
}

// maxRAM is the maximum MB of RAM that can to be free in the pool. If it's zero, it's not going to use it
func (r *Rata) maxRAM(hypers []*isardvdi.OrchestratorHypervisor) int {
	if r.cfg.MaxRAMHourly != nil {
		return getCurrentHourlyLimit(r.cfg.MaxRAMHourly, time.Now())
	}

	if r.cfg.MaxRAM != 0 {
		return r.cfg.MaxRAM
	}

	if r.cfg.MaxRAMLimitPercent != 0 {
		margin := 0
		if r.cfg.MaxRAMLimitMarginHourly != nil {
			margin = getCurrentHourlyLimit(r.cfg.MaxRAMLimitMarginHourly, time.Now())
		} else {
			margin = r.cfg.MaxRAMLimitMargin
		}

		maxRAM := 0
		for _, h := range hypers {
			maxRAM += (h.MinFreeMemGB * 1024) // we want it as MB, not GB
		}

		maxRAM = int(math.Round((float64(r.cfg.MaxRAMLimitPercent) / 100.0) * float64(maxRAM)))
		maxRAM += margin

		return maxRAM
	}

	return 0
}

func (r *Rata) classifyHypervisors(hypers []*isardvdi.OrchestratorHypervisor) ([]*isardvdi.OrchestratorHypervisor, []*isardvdi.OrchestratorHypervisor, []*isardvdi.OrchestratorHypervisor) {
	// hypersToAcknowledge are the hypervisors that need to be taken into account for all the calculations by this director
	hypersToAcknowledge := []*isardvdi.OrchestratorHypervisor{}
	// hypersToHandle are the hypervisors that can be handled by this director
	hypersToHandle := []*isardvdi.OrchestratorHypervisor{}
	// hypersOnDeadRow are the hypervisors that we can handle and are on the dead row
	hypersOnDeadRow := []*isardvdi.OrchestratorHypervisor{}

	for _, h := range hypers {
		// Check if we need to acknowledge the hypervisor
		if h.Status == isardvdi.HypervisorStatusOnline &&
			!h.Buffering &&
			!h.GPUOnly {

			if !h.OnlyForced {
				hypersToAcknowledge = append(hypersToAcknowledge, h)
			}

			// Ensure we don't play with non orchestrator managed hypervisors! :)
			if h.OrchestratorManaged {
				hypersToHandle = append(hypersToHandle, h)

				// Check if the hypervisor is in the dead row
				if !h.DestroyTime.IsZero() {
					hypersOnDeadRow = append(hypersOnDeadRow, h)
				}
			}
		}
	}

	return hypersToAcknowledge, hypersToHandle, hypersOnDeadRow
}

func (r *Rata) hyperResourcesAvail(hyper *isardvdi.OrchestratorHypervisor) (int, int) {
	cpuAvail := hyper.CPU.Free
	// Don't take into account the memory that's reserved by the hypervisors (we want it in MB)
	// and neither take into account the extra orchestrator memory reservation
	ramAvail := hyper.RAM.Free - (hyper.MinFreeMemGB * 1024) - r.cfg.HyperMinRAM

	return cpuAvail, ramAvail
}

// TODO: CPU
// TODO: Capabilities
func (r *Rata) bestHyperToCreate(hypersAvail []*operationsv1.ListHypervisorsResponseHypervisor, minCPU, minRAM int) (string, error) {
	var bestHyper *operationsv1.ListHypervisorsResponseHypervisor

	for _, h := range hypersAvail {
		if h.State == operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE {
			enoughRAM := h.Ram > int32(minRAM)

			if bestHyper != nil {
				// Pick the smallest hypervisor that can provide the required
				if enoughRAM && h.Ram < bestHyper.Ram {
					bestHyper = h
				}

				// Check if the current hyper can satisfy the requirements
			} else if enoughRAM {
				bestHyper = h
			}
		}
	}

	if bestHyper == nil {
		return "", ErrNoHypervisorAvailable
	}

	return bestHyper.Id, nil
}

// TODO: CPU
// TODO: Capabilities
func (r *Rata) bestHyperToPardon(hypersOnDeadRow []*isardvdi.OrchestratorHypervisor, ramAvail, minCPU, minRAM int) *isardvdi.OrchestratorHypervisor {
	var hyperToPardon *isardvdi.OrchestratorHypervisor

	for _, h := range hypersOnDeadRow {
		enoughRAM := ramAvail+h.RAM.Free > minRAM

		if hyperToPardon != nil {
			// Get the hypervisor that has the furthest destroy time
			if enoughRAM && h.DestroyTime.Compare(hyperToPardon.DestroyTime) == 1 {
				hyperToPardon = h
			}

		} else if enoughRAM {
			hyperToPardon = h
		}
	}

	return hyperToPardon
}

func (r *Rata) bestHyperToDestroy(hypersToHandle []*isardvdi.OrchestratorHypervisor) *isardvdi.OrchestratorHypervisor {
	for _, h := range hypersToHandle {
		// Check if we need to kill the hypervisor (because it's time to kill it or it has 0 desktops started)
		if !h.DestroyTime.IsZero() && (h.DestroyTime.Before(time.Now()) || h.DesktopsStarted == 0) {
			return h
		}
	}

	return nil
}

// TODO: CPU
// TODO: Capabilities
func (r *Rata) bestHyperToMoveInDeadRow(hypersToHandle []*isardvdi.OrchestratorHypervisor, ramAvail, minCPU, minRAM, maxRAM int) *isardvdi.OrchestratorHypervisor {
	var deadRow *isardvdi.OrchestratorHypervisor

	for _, h := range hypersToHandle {
		// Ensure the hypervisor is not on the dead row
		canBeSentenced := h.DestroyTime.IsZero() &&
			(
			// If the hypervisor is only forced, the maxRAM límit is set and we've reached the maxRAM limit
			// (we don't need to check if we can remove it, since it's already not being counted for the ramAvail limit)
			(h.OnlyForced && maxRAM > 0 && ramAvail > maxRAM) ||
				// If the maxRAM limit is set and if we remove it, we'll have enough RAM to meet the minRAM limit
				(maxRAM > 0 && ramAvail > maxRAM && ramAvail-h.RAM.Free > minRAM))

		if canBeSentenced && deadRow != nil {
			// Pick the biggest hypervisor to kill
			if h.RAM.Total > deadRow.RAM.Total {
				deadRow = h
			}

		} else if canBeSentenced {
			deadRow = h
		}
	}

	return deadRow
}

// TODO: Start a smaller available hypervisor in order to scale down afterwards
func (r *Rata) NeedToScaleHypervisors(ctx context.Context, operationsHypers []*operationsv1.ListHypervisorsResponseHypervisor, hypers []*isardvdi.OrchestratorHypervisor) (*operationsv1.CreateHypervisorsRequest, *operationsv1.DestroyHypervisorsRequest, []string, []string, error) {
	operationsHypersAvail := []*operationsv1.ListHypervisorsResponseHypervisor{}
availHypersLoop:
	for _, h := range operationsHypers {
		for _, hyp := range hypers {
			if h.Id == hyp.ID {
				// If it's already in IsardVDI, don't add it as available
				continue availHypersLoop
			}
		}

		operationsHypersAvail = append(operationsHypersAvail, h)
	}

	hypersToAcknowledge, hypersToHandle, hypersOnDeadRow := r.classifyHypervisors(hypers)

	minCPU := r.minCPU()
	minRAM := r.minRAM(hypersToAcknowledge)
	maxRAM := r.maxRAM(hypersToAcknowledge)

	cpuAvail := 0
	ramAvail := 0
	for _, h := range hypersToAcknowledge {
		cpu, ram := r.hyperResourcesAvail(h)

		cpuAvail += cpu
		ramAvail += ram
	}

	r.log.Debug().Int("cpu_avail", cpuAvail).Int("ram_avail", ramAvail).Int("min_ram", minRAM).Int("max_ram", maxRAM).Msg("available resources")

	// TODO: CPU
	// Scale up
	reqHypersCPU := 0
	if minCPU > 0 {
		hasEnough := cpuAvail / minCPU
		if hasEnough == 0 {
			reqHypersCPU = minCPU - cpuAvail
		}
	}

	reqHypersRAM := 0
	if minRAM > 0 {
		hasEnough := ramAvail / minRAM
		if hasEnough == 0 {
			reqHypersRAM = minRAM - ramAvail
		}
	}

	// Check for scale up
	if reqHypersCPU != 0 || reqHypersRAM != 0 {
		// Check if we have hypervisors on the dead row, if it's the case, remove those from it
		hyperToPardon := r.bestHyperToPardon(hypersOnDeadRow, ramAvail, minCPU, minRAM)
		if hyperToPardon != nil {
			r.log.Info().Str("id", hyperToPardon.ID).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "up").Msg("cancel hypervisor destruction")
			return nil, nil, []string{hyperToPardon.ID}, nil, nil
		}

		// If not, create a new hypervisor
		id, err := r.bestHyperToCreate(operationsHypersAvail, reqHypersCPU, reqHypersRAM)
		if err != nil {
			return nil, nil, nil, nil, err
		}

		r.log.Info().Str("id", id).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "up").Msg("create hypervisor to scale up")
		return &operationsv1.CreateHypervisorsRequest{
			Ids: []string{id},
		}, nil, nil, nil, nil
	}

	// Scale down
	hyperToDestroy := r.bestHyperToDestroy(hypersToHandle)
	if hyperToDestroy != nil {
		r.log.Info().Str("id", hyperToDestroy.ID).Str("scaling", "down").Msg("destroy hypervisor")
		return nil, &operationsv1.DestroyHypervisorsRequest{Ids: []string{hyperToDestroy.ID}}, nil, nil, nil
	}

	// Check if we need to move the hypervisor to the dead row
	deadRow := r.bestHyperToMoveInDeadRow(hypersToHandle, ramAvail, minCPU, minRAM, maxRAM)
	if deadRow != nil {
		r.log.Info().Str("id", deadRow.ID).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "down").Msg("set hypervisor to destroy")
		return nil, nil, nil, []string{deadRow.ID}, nil
	}

	return nil, nil, nil, nil, nil
}

func (r *Rata) ExtraOperations(ctx context.Context, hypers []*isardvdi.OrchestratorHypervisor) error {
	_, hypersToManage, _ := r.classifyHypervisors(hypers)
	for _, h := range hypersToManage {
		// Don't run extra operations on hypervisors on the dead row
		if h.DestroyTime.IsZero() {
			_, freeRAM := r.hyperResourcesAvail(h)

			switch h.OnlyForced {
			// Set the hypervisors to only forced if there's too much load
			case false:
				if r.cfg.HyperMinCPU != 0 && (h.CPU.Free <= r.cfg.HyperMinCPU) ||
					r.cfg.HyperMinRAM != 0 && (freeRAM <= r.cfg.HyperMinRAM) {

					if r.dryRun {
						r.log.Info().Bool("DRY_RUN", true).Int("free_cpu", h.CPU.Free).Int("free_ram", freeRAM).Int("hyper_min_cpu", r.cfg.HyperMinCPU).Int("hyper_min_ram", r.cfg.HyperMinRAM).Msg("set hypervisor to only_forced")

					} else {
						if err := r.apiCli.AdminHypervisorOnlyForced(ctx, h.ID, true); err != nil {
							return fmt.Errorf("set hypervisor '%s' to only_forced: %w", h.ID, err)
						}

						r.log.Info().Str("id", h.ID).Int("free_cpu", h.CPU.Free).Int("free_ram", freeRAM).Int("hyper_min_cpu", r.cfg.HyperMinCPU).Int("hyper_min_ram", r.cfg.HyperMinRAM).Msg("set hypervisor to only_forced")
					}

				}

				// Remove the hypervisor from only forced if the hypervisor has availiable resources
			case true:
				if r.cfg.HyperMaxCPU != 0 && (h.CPU.Free > r.cfg.HyperMaxCPU) ||
					r.cfg.HyperMaxRAM != 0 && (freeRAM > r.cfg.HyperMaxRAM) {

					if r.dryRun {
						r.log.Info().Bool("DRY_RUN", true).Int("free_cpu", h.CPU.Free).Int("free_ram", freeRAM).Int("hyper_max_cpu", r.cfg.HyperMaxCPU).Int("hyper_max_ram", r.cfg.HyperMaxRAM).Msg("remove hypervisor from only_forced")

					} else {
						if err := r.apiCli.AdminHypervisorOnlyForced(ctx, h.ID, false); err != nil {
							return fmt.Errorf("set hypervisor '%s' to only_forced: %w", h.ID, err)
						}

						r.log.Info().Str("id", h.ID).Int("free_cpu", h.CPU.Free).Int("free_ram", freeRAM).Int("hyper_max_cpu", r.cfg.HyperMaxCPU).Int("hyper_max_ram", r.cfg.HyperMaxRAM).Msg("remove hypervisor from only_forced")
					}

				}
			}
		}
	}

	return nil
}

/*
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
++++++++++++++++++++++++++++++++++++##%%%*++++++++++++++++++++++++++++++++++++++
+++++++++++++++++++++++++++++++++++#%%%##%++++++++++++++++++++++++++++++++++++++
++++++++++++++++++++++++++++++++++#%%%%%%#*+++++++++++++++++++++++++++++++++++++
++++++++++++++++++++++++++++++++++#%%%%%%##++++++++++++++++++***++++++++++++++++
++++++++++++++++++++++++++++++++++#%%%%%%###*++++*##%%##*#*#%%%%%#++++++++++++++
++++++++++++++++++++++++++++++++++#%%%%%%%%#%%#%%%####%%%#########*+++++++++++++
+++++++++++++++++++++++++++++++++++#%%%%%%%%%%%%%**##**%%%**####***+++++++++++++
+++++++++++++++++++++++++++++++++++++**%%%%%%%%%%##%@%%%%%@#+*%#**++++++++++++++
++++++++++++++++++++++++++++++++++++++#%@@@%%%%%%%%%%%%%%%%%**%%#*++++++++++++++
+++++++++++++++++++++++++++++++++++++*%@@@@@@%%%%%%%%%%%%%%%%#####++++++++++++++
+++++++++++++++++++++++++++++++++++++#%@@@@@@@@%%%%#%%%%%#########*+++++++++++++
++++++++++++++++++++++++++++++++++++#%@@@@@@@@@@%%%%%%%%%#########*+++++++++++++
+++++++++++++++++++++++++++++++++++*%@@@@@@@@@@@@%%%%@@@@@@%%#%%%#++++++++++++++
++++++++++++++++++++++++++++++++++*%%@@@@@@@@@@@@@%%%@@@@@@@%%%%%*++++++++++++++
+++++++++++++++++++++++++++++++++*%%@@@@@@@@@@@@@@@@%@@@@%%%%%%%*+++++++++++++++
++++++++++++++++++++++++++++++++*%%@@@@@@@@@@@@@@@@@@%%%@%%%%%%%*+++++++++++++++
+++++++++++++++++++++++++++++++#%@@@@@@@@%%@@@@@@@@@@@@@@@%%%%%%*+++++++++++++++
+++++++++++++++++++++++++++++*%%@@@@@@@#%%%@@@@@@@@@@@@@@%%%%%%%#+++++++++++++++
++++++++++++++++++++++++++++#%%%@@@@@@%###%@@%@@@@@@@@@@@@%%%%%%#*++++++++++++++
++++++++++++++++++++++++++*#%%%%%@@@@@%#*#%%#%@@@@@@@@@@@%%%%%%%%#*+++++++++++++
++++++++++++++++++++++++++#%%%%%@@@@@@%##**#%@@@@@@@@@@@%%%%%%%%%%#+++++++++++++
+++++++++++++++++++++++++#%%%%%%%@@@@@%%%%%%%%%%%%%%%%%%%%%%%%%%%%%#++++++++++++
++++++++++++++++++++++++#%@@%%%%%%@@@@@@%%%%%%%%%%%%%%%%%%%%%%%@%%%%#+++++++++++
+++++++++++++++++++++++#%@@@@@@@@@@@@@@%%%%%%%%%%%%%%%%%%%@@@@@@%%%%#*++++++++++
+++++++++++++++++++++*%%%%@%%%@@@@@@%%%%%%%%%%%%%%%%%%%%#####%%%%%%%#+++++++++++
+++++++++++++++++++++#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%###**#%%%%%%#*++++++++++
++++++++++++++++++++*%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%#%%%########*+++++++++
++++++++++++++++++++#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%###%%%%%%##########*++++++++
+++++++++++++++++++*%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%#%%%%%%######%###%####*++++++
++++++++++++++++++*%%%%%@%%@%%@%%@%%%%%%%%%%%%%%%%%%%%##############%%%%%%*+++++
+++++++++++++++++*%@%@%@@@@%@@%@@%@%%%%%%%@%%%%%%%%%%%########%#%%%%%%%%%%#*++++
+++++++++++++++++#%@@@@@@@@@@@@@@%@@@@%%@%@%%%%%%%%%%%%#%##%%%%##%%%%%%%%%%#*+++
+++++++++++++++++%@@@@@@@@@@@@@@@@@@@@@@%%%%%%%%%%%%%%%%#%##%%%%%%%#%%%%%%%%#+++
+++++++++++++++++%@@@@@@@@@@@@@@@@@@@@@@%@@%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%*++
++++++++++++++++*%@@@@@@@@@@@@@@@@@@@@@@@@@@%@@%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%*+
++++++++++++++++#%%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%%@%%%@@@@@%##@%##%%%%%%++
++++++++++++++++*#%@@@@@@@@@@@@@@@@%%@@%##@@@@@@@@@@@@@@@@@@@@@@@@%##@%#%%%%%%*+
+++++++++++**###%%@@@@@@@@@@@@@@@@%###@%##@@@@@@@@@@@@@@@@@@@@@@@@@%#%%%%%*%%#*+
++++*##%%%%####**#%@@@@@@@@@@@@@@@@%%##%##@@@@@@@@@@@@@@@@@@@@@@@@@@%%#%%%%%%#++
++*%#**+++++++++++*#%@@@@@@@@@@@@@%###***%@@@@@@@@@@@@@@@@@@@@@@@@@%%###%%%%%*++
++***++++++++++++++*#%@@@@@@@@@@@@@@%%#**#@@@@@@@@@@@@@@@@@@@@@@@@@%##%%%%%#*+++
+++++*****+++++++++++*#%@@@@@@@@@@@@@@%#**@@@@@@@@@@@@@@@@@@@@@@@@%##%@@%#++++++
+++++++++++++++++++++++*##%@@@@@@@@@@@@%#*#%@@%%%%%%###**#*****#%%%###**++++++++
+++++++++++++++++++++++++++*####%%%%@@@@%##*+++++++++++++++++++++**+++++++++++++
++++++++++++++++++++++++++++++++++++++++***+++++++++++++++++++++++++++++++++++++
*/
