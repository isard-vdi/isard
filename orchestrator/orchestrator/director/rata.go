package director

import (
	"context"
	"fmt"
	"sort"
	"time"

	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/jwt"

	"github.com/rs/zerolog"
)

const DirectorTypeRata = "rata"

// Rata is a director that has some minimum values required.
// It waits until there are less values than the minimum, then it takes action
type Rata struct {
	cfg cfg.DirectorRata
	// hyperMinCPU is the minimum CPU number that a hypervisor needs to have in order to run.
	// If it reaches the limit, the hypervisor is put at OnlyForced, which prevents more desktops to be started in the hypervisor
	hyperMinCPU int
	// hyperMinRAM is the minimum MB of RAM that a hypervisor needs to have in order to run.
	// If it reaches the limit, the hypervisor is put at OnlyForced, which prevents more desktops to be started in the hypervisor
	hyperMinRAM int

	apiCli    client.Interface
	apiSecret string

	log *zerolog.Logger
}

func NewRata(cfg cfg.Orchestrator, log *zerolog.Logger, apiCli client.Interface) *Rata {
	return &Rata{
		cfg:         cfg.DirectorRata,
		hyperMinCPU: cfg.DirectorRata.HyperMinCPU,
		hyperMinRAM: cfg.DirectorRata.HyperMinRAM,

		apiSecret: cfg.APISecret,
		apiCli:    apiCli,

		log: log,
	}
}

func (r *Rata) String() string {
	return DirectorTypeRata
}

func getCurrentHourlyLimit(limit map[time.Time]int, now time.Time) int {
	times := []time.Time{}
	for k := range limit {
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
				return limit[t]
			}

			// If it's not the first, take the previous limit, since it's the active right now
			return limit[times[i-1]]
		}

		// If it's the last item in the list, take it, since it's the active right now
		if i == len(times)-1 {
			return limit[t]
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
func (r *Rata) minRAM() int {
	if r.cfg.MinRAMHourly == nil {
		return r.cfg.MinRAM
	}

	return getCurrentHourlyLimit(r.cfg.MinRAMHourly, time.Now())
}

// TODO: Stop hypervisors
func (r *Rata) NeedToScaleHypervisors(ctx context.Context, hypers []*model.Hypervisor) (*operationsv1.CreateHypervisorRequest, *operationsv1.DestroyHypervisorRequest, error) {
	cpuAvail := 0
	ramAvail := 0

	for _, h := range hypers {
		if h.Status == client.HypervisorStatusOnline && !h.OnlyForced {
			cpuAvail += h.CPU.Free
			ramAvail += h.RAM.Free
		}
	}

	reqHypersCPU := 0
	if r.minCPU() > 0 {
		hasEnough := cpuAvail / r.minCPU()
		if hasEnough == 0 {
			reqHypersCPU = r.minCPU() - cpuAvail
		}
	}

	reqHypersRAM := 0
	if r.minRAM() > 0 {
		hasEnough := ramAvail / r.minRAM()
		if hasEnough == 0 {
			reqHypersRAM = r.minRAM() - ramAvail
		}
	}

	var create *operationsv1.CreateHypervisorRequest
	if reqHypersCPU != 0 || reqHypersRAM != 0 {
		create = &operationsv1.CreateHypervisorRequest{
			MinCpu: int32(reqHypersCPU),
			MinRam: int32(reqHypersRAM),
		}

		r.log.Info().Int("avail_cpu", cpuAvail).Int("avail_ram", ramAvail).Int("req_cpu", reqHypersCPU).Int("req_ram", reqHypersRAM).Msg("create hypervisor")
	}

	return create, nil, nil
}

func (r *Rata) ExtraOperations(ctx context.Context, hypers []*model.Hypervisor) error {
	for _, h := range hypers {
		if (r.hyperMinCPU != 0 && (h.CPU.Free <= r.hyperMinCPU) ||
			r.hyperMinRAM != 0 && (h.RAM.Free <= r.hyperMinRAM)) &&
			h.Status == client.HypervisorStatusOnline &&
			!h.OnlyForced {

			var err error
			tkn, err := jwt.SignAPIJWT(r.apiSecret)
			if err != nil {
				return fmt.Errorf("sign JWT token for calling the API: %w", err)
			}

			r.apiCli.SetToken(tkn)

			if err := r.apiCli.AdminHypervisorOnlyForced(ctx, h.ID, true); err != nil {
				return fmt.Errorf("set hypervisor '%s' to only_forced: %w", h.ID, err)
			}

			r.log.Info().Int("free_cpu", h.CPU.Free).Int("free_ram", h.RAM.Free).Int("hyper_min_cpu", r.hyperMinCPU).Int("hyper_min_ram", r.hyperMinRAM).Msg("set hypervisor to only_forced")
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
