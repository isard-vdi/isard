package director

import (
	"context"
	"fmt"
	"math"
	"sort"
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
	// hyperMinCPU is the minimum CPU number that a hypervisor needs to have in order to run.
	// If it reaches the limit, the hypervisor is put at OnlyForced, which prevents more desktops to be started in the hypervisor
	hyperMinCPU int
	// hyperMinRAM is the minimum MB of RAM that a hypervisor needs to have in order to run.
	// If it reaches the limit, the hypervisor is put at OnlyForced, which prevents more desktops to be started in the hypervisor
	hyperMinRAM int
	// hyperMaxCPU is the maximum CPU number that a hypervisor can have while being OnlyForced.
	// If it reaches the limit, the hypervisor is removed from OnlyForced
	hyperMaxCPU int
	// hyperMaxRAM is the maximum MB of RAM that a hypervisor can have while being OnlyForced.
	// If it reaches the limit, the hypervisor is removed from OnlyForced
	hyperMaxRAM int

	apiCli isardvdi.Interface

	log *zerolog.Logger
}

func NewRata(cfg cfg.DirectorRata, dryRun bool, log *zerolog.Logger, apiCli isardvdi.Interface) *Rata {
	return &Rata{
		cfg:         cfg,
		dryRun:      dryRun,
		hyperMinCPU: cfg.HyperMinCPU,
		hyperMinRAM: cfg.HyperMinRAM,
		hyperMaxCPU: cfg.HyperMaxCPU,
		hyperMaxRAM: cfg.HyperMaxRAM,

		apiCli: apiCli,

		log: log,
	}
}

func (r *Rata) String() string {
	return DirectorTypeRata
}

func getCurrentHourlyLimit(limit map[time.Weekday]map[time.Time]int, now time.Time) int {
	weekdays := []time.Weekday{}
	for d := range limit {
		weekdays = append(weekdays, d)
	}

	sort.Slice(weekdays, func(i, j int) bool {
		return weekdays[i] < weekdays[j]
	})

	var weekday time.Weekday = -1
	for _, d := range weekdays {
		// If today is in the limit weekdays, use it
		if d == now.Weekday() {
			weekday = d
			break
		}

		// If we've "passed" today's weekday (e.g. today is wednesday and 'd' is thursday), use the last day that we had (tuesday)
		if d > now.Weekday() {
			// Unless there's no previous day. In that case, we should get the last day of the week available (e.g. today is monday, 'd' is tuesday. We should get sunday in that case [or whatever the last day is])
			if weekday == -1 {
				weekday = weekdays[len(weekdays)-1]
			}

			break
		}

		weekday = d
	}

	times := []time.Time{}
	for k := range limit[weekday] {
		times = append(times, k)
	}

	sort.Slice(times, func(i, j int) bool {
		return times[i].Before(times[j])
	})

	for i, t := range times {
		hour := time.Date(0, time.January, 1, now.Hour(), now.Minute(), 0, 0, time.UTC)

		if hour.Before(t) {
			// If is the first hour, it will take it as the first
			if i == 0 {
				return limit[weekday][t]
			}

			// If it's not the first, take the previous limit, since it's the active right now
			return limit[weekday][times[i-1]]
		}

		// If it's the last item in the list, take it, since it's the active right now
		if i == len(times)-1 {
			return limit[weekday][t]
		}
	}

	panic("invalid rata director hourly minimum")
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

func (r *Rata) maxRAM() int {
	if r.cfg.MaxRAMHourly == nil {
		return r.cfg.MaxRAM
	}

	return getCurrentHourlyLimit(r.cfg.MaxRAMHourly, time.Now())
}

// TODO: Start a smaller available hypervisor in order to scale down afterwards
func (r *Rata) NeedToScaleHypervisors(ctx context.Context, operationsHypers []*operationsv1.ListHypervisorsResponseHypervisor, hypers []*isardvdi.OrchestratorHypervisor) (*operationsv1.CreateHypervisorsRequest, *operationsv1.DestroyHypervisorsRequest, []string, []string, error) {
	var (
		cpuAvail = 0
		ramAvail = 0
	)

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

	hypersAvail := []*isardvdi.OrchestratorHypervisor{}
	hypersOnDeadRow := []*isardvdi.OrchestratorHypervisor{}
	for _, h := range hypers {
		switch h.Status {
		case isardvdi.HypervisorStatusOnline:
			if h.DestroyTime.IsZero() {
				// Ensure we don't play with buffering hypervisors! :)
				if !h.Buffering {
					if !h.OnlyForced && !h.GPUOnly {
						// It's online, is not forced to GPUs and not only forced, count it as available resources
						cpuAvail += h.CPU.Free
						ramAvail += h.RAM.Free
						hypersAvail = append(hypersAvail, h)
					}
				}

			} else {
				// Only work with orchestrator managed hypervisors
				if h.OrchestratorManaged {
					hypersOnDeadRow = append(hypersOnDeadRow, h)
				}
			}
		}
	}

	minRAM := r.minRAM(hypersAvail)

	r.log.Debug().Int("cpu_avail", cpuAvail).Int("ram_avail", ramAvail).Int("min_ram", minRAM).Int("max_ram", r.maxRAM()).Msg("available resources")

	reqHypersCPU := 0
	if r.minCPU() > 0 {
		hasEnough := cpuAvail / r.minCPU()
		if hasEnough == 0 {
			reqHypersCPU = r.minCPU() - cpuAvail
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
		var hyperToPardon *isardvdi.OrchestratorHypervisor
		if len(hypersOnDeadRow) != 0 {
			// TODO: CPU
			for _, h := range hypersOnDeadRow {
				if hyperToPardon != nil {
					if ramAvail+h.RAM.Free > minRAM && h.RAM.Total < hyperToPardon.RAM.Total {
						hyperToPardon = h
					}

				} else {
					if ramAvail+h.RAM.Free > minRAM {
						hyperToPardon = h
					}
				}
			}
		}

		if hyperToPardon != nil {
			r.log.Info().Str("id", hyperToPardon.ID).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "up").Msg("cancel hypervisor destruction")
			return nil, nil, []string{hyperToPardon.ID}, nil, nil

		} else {
			// If not, create a new hypervisor
			id, err := rataBestHyperToCreate(operationsHypersAvail, reqHypersCPU, reqHypersRAM)
			if err != nil {
				return nil, nil, nil, nil, err
			}

			r.log.Info().Str("id", id).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "up").Msg("create hypervisor to scale up")
			return &operationsv1.CreateHypervisorsRequest{
				Ids: []string{id},
			}, nil, nil, nil, nil
		}
	}

	// Check for scale down
	hypersToMoveInTheDeadRow := []*isardvdi.OrchestratorHypervisor{}
	for _, h := range hypers {
		switch h.Status {
		case isardvdi.HypervisorStatusOnline:
			// Ensure we don't play with buffering hypervisors or non orchestrator managed ones! :)
			if !h.Buffering && h.OrchestratorManaged {

				// Check if we need to kill the hypervisor (because it's time to kill it or it has 0 desktops started)
				if !h.DestroyTime.IsZero() && (h.DestroyTime.Before(time.Now()) || h.DesktopsStarted == 0) {
					r.log.Info().Str("id", h.ID).Str("scaling", "down").Msg("destroy hypervisor")
					return nil, &operationsv1.DestroyHypervisorsRequest{Ids: []string{h.ID}}, nil, nil, nil

				} else {
					// Check if we need to move the hypervisor to the dead row
					// TODO: CPU
					if h.DestroyTime.IsZero() && ((h.OnlyForced && r.maxRAM() > 0 && r.maxRAM() < ramAvail) || (r.maxRAM() > 0 && r.maxRAM() < ramAvail-h.RAM.Free)) {
						hypersToMoveInTheDeadRow = append(hypersToMoveInTheDeadRow, h)
					}
				}
			}
		}
	}

	// Only move a hypervisor to the dead row
	var deadRow *isardvdi.OrchestratorHypervisor
	for _, h := range hypersToMoveInTheDeadRow {
		if deadRow != nil {
			// Pick the biggest hypervisor to kill
			if h.RAM.Total > deadRow.RAM.Total {
				deadRow = h
			}

		} else {
			deadRow = h
		}
	}

	if deadRow != nil {
		r.log.Info().Str("id", deadRow.ID).Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Str("scaling", "down").Msg("set hypervisor to destroy")
		return nil, nil, nil, []string{deadRow.ID}, nil
	}

	return nil, nil, nil, nil, nil
}

// TODO: CPU
// TODO: Capabilities
func rataBestHyperToCreate(avail []*operationsv1.ListHypervisorsResponseHypervisor, minCPU, minRAM int) (string, error) {
	var bestHyper *operationsv1.ListHypervisorsResponseHypervisor
	for _, h := range avail {
		if h.State == operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE {
			if bestHyper != nil {
				// Pick the smallest hypervisor that can provide the required
				if h.Ram > int32(minRAM) && h.Ram < bestHyper.Ram {
					bestHyper = h
				}

			} else {
				// Check if the current hyper can satisfy the requirements
				if h.Ram > int32(minRAM) {
					bestHyper = h
				}
			}
		}
	}

	if bestHyper == nil {
		return "", ErrNoHypervisorAvailable
	}

	return bestHyper.Id, nil
}

func (r *Rata) ExtraOperations(ctx context.Context, hypers []*isardvdi.OrchestratorHypervisor) error {
	for _, h := range hypers {
		switch h.Status {
		case isardvdi.HypervisorStatusOnline:
			// Ensure we don't play with buffering hypervisors or hypers on the dead row or non orchestrator managed! :)
			if !h.Buffering && h.OrchestratorManaged && h.DestroyTime.IsZero() {

				switch h.OnlyForced {
				case false:
					// Set the hypervisors to only forced if there's too much load
					if r.hyperMinCPU != 0 && (h.CPU.Free <= r.hyperMinCPU) ||
						r.hyperMinRAM != 0 && (h.RAM.Free <= r.hyperMinRAM) {

						if r.dryRun {
							r.log.Info().Bool("DRY_RUN", true).Int("free_cpu", h.CPU.Free).Int("free_ram", h.RAM.Free).Int("hyper_min_cpu", r.hyperMinCPU).Int("hyper_min_ram", r.hyperMinRAM).Msg("set hypervisor to only_forced")

						} else {
							if err := r.apiCli.AdminHypervisorOnlyForced(ctx, h.ID, true); err != nil {
								return fmt.Errorf("set hypervisor '%s' to only_forced: %w", h.ID, err)
							}

							r.log.Info().Str("id", h.ID).Int("free_cpu", h.CPU.Free).Int("free_ram", h.RAM.Free).Int("hyper_min_cpu", r.hyperMinCPU).Int("hyper_min_ram", r.hyperMinRAM).Msg("set hypervisor to only_forced")
						}

					}

				case true:
					// Remove the hypervisor from only forced if the hypervisor has availiable resources
					if r.hyperMaxCPU != 0 && (h.CPU.Free > r.hyperMaxCPU) ||
						r.hyperMaxRAM != 0 && (h.RAM.Free > r.hyperMaxRAM) {

						if r.dryRun {
							r.log.Info().Bool("DRY_RUN", true).Int("free_cpu", h.CPU.Free).Int("free_ram", h.RAM.Free).Int("hyper_max_cpu", r.hyperMaxCPU).Int("hyper_max_ram", r.hyperMaxRAM).Msg("remove hypervisor from only_forced")

						} else {
							if err := r.apiCli.AdminHypervisorOnlyForced(ctx, h.ID, false); err != nil {
								return fmt.Errorf("set hypervisor '%s' to only_forced: %w", h.ID, err)
							}

							r.log.Info().Str("id", h.ID).Int("free_cpu", h.CPU.Free).Int("free_ram", h.RAM.Free).Int("hyper_max_cpu", r.hyperMaxCPU).Int("hyper_max_ram", r.hyperMaxRAM).Msg("remove hypervisor from only_forced")
						}

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
