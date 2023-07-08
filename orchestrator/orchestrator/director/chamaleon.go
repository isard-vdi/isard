package director

import (
	"context"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/orchestrator/log"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	combinations "github.com/mxschmitt/golang-combinations"
	"github.com/rs/zerolog"
)

const (
	DirectorTypeChamaleon = "chamaleon"
)

type Chamaleon struct {
	apiCli isardvdi.Interface

	log *zerolog.Logger
}

func NewChamaleon(log *zerolog.Logger, apiCli isardvdi.Interface) *Chamaleon {
	return &Chamaleon{
		apiCli: apiCli,
		log:    log,
	}
}

func (c *Chamaleon) String() string {
	return DirectorTypeChamaleon
}

func (c *Chamaleon) NeedToScaleHypervisors(ctx context.Context, operationsHypers []*operationsv1.ListHypervisorsResponseHypervisor, hypers []*isardvdi.OrchestratorHypervisor) (*operationsv1.CreateHypervisorsRequest, *operationsv1.DestroyHypervisorsRequest, []string, []string, error) {
	operationsHypersAvail := []*operationsv1.ListHypervisorsResponseHypervisor{}
availHypersLoop:
	for _, h := range operationsHypers {
		hasGPU := false
		for _, cap := range h.Capabilities {
			if cap == operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU {
				hasGPU = true
			}
		}

		if !hasGPU {
			continue availHypersLoop
		}

		for _, hyp := range hypers {
			if h.Id == hyp.ID {
				// If it's already in IsardVDI, don't add it as available
				continue availHypersLoop
			}
		}

		operationsHypersAvail = append(operationsHypersAvail, h)
	}

	totalUnits := map[string]int{}

	hypersAvail := []*isardvdi.OrchestratorHypervisor{}
	hypersOnDeadRow := []*isardvdi.OrchestratorHypervisor{}
	for _, h := range hypers {
		switch h.Status {
		case isardvdi.HypervisorStatusOnline:
			if h.DestroyTime.IsZero() {
				// Ensure we don't play with buffering hypervisors! :)
				if !h.Buffering && !h.OnlyForced && len(h.GPUs) != 0 {
					// It's online, has GPUs and not only forced, count it as available resources
					for _, g := range h.GPUs {
						totalUnits[g.Profile] += g.TotalUnits
					}

					// Only work with hypervisors we manage
					if h.OrchestratorManaged {
						hypersAvail = append(hypersAvail, h)
					}
				}
			} else {
				// Only work with orchestrator managed hypervisors
				if h.OrchestratorManaged && len(h.GPUs) != 0 {
					hypersOnDeadRow = append(hypersOnDeadRow, h)
				}
			}
		}
	}

	bookings, err := c.apiCli.OrchestratorGPUBookingList(ctx)
	if err != nil {
		return nil, nil, nil, nil, fmt.Errorf("get bookings list: %w", err)
	}

	c.log.Debug().Array("bookings", log.NewModelBookings(bookings)).Object("total_units", log.NewModelMapStrInt(totalUnits)).Msg("available resources")

	reqHypersUnits := map[string]int{}
	for _, b := range bookings {
		// Check that we have enough units for the current bookings, and for the future ones
		t := chamaleonMaximumBookings(b.Now, b.Create)
		if t.Units > 0 {
			hasEnough := totalUnits[b.Profile] / t.Units
			if hasEnough == 0 {
				reqHypersUnits[b.Profile] = t.Units - totalUnits[b.Profile]
			}
		}
	}

	// Check for scale up
	if len(reqHypersUnits) != 0 {
		// Check if we have hypervisors on the dead row, if it's the case, remove those from it
		if len(hypersOnDeadRow) != 0 {
			// We can ignore the error here, since it can only return that has not enough hypervisors, and in that case we need to attempt
			// to create more
			hypersToPardon, _ := chamaleonBestHypersToCreateIsardVDI(hypersOnDeadRow, reqHypersUnits)

			if len(hypersToPardon) != 0 {
				c.log.Info().Array("ids", log.NewModelStrArray(hypersToPardon)).Object("total_units", log.NewModelMapStrInt(totalUnits)).Object("req_units", log.NewModelMapStrInt(reqHypersUnits)).Str("scaling", "up").Msg("cancel hypervisors destruction")
				return nil, nil, hypersToPardon, nil, nil
			}
		}

		// If we don't have hypers on the dead row, create the best hypervisor combination
		ids, err := chamaleonBestHypersToCreate(operationsHypersAvail, reqHypersUnits)
		if err != nil {
			return nil, nil, nil, nil, err
		}

		c.log.Info().Array("ids", log.NewModelStrArray(ids)).Object("total_units", log.NewModelMapStrInt(totalUnits)).Object("req_units", log.NewModelMapStrInt(reqHypersUnits)).Str("scaling", "up").Msg("create hypervisors to scale up")
		return &operationsv1.CreateHypervisorsRequest{
			Ids: ids,
		}, nil, nil, nil, nil
	}

	// Check for scale down
	hypersToDestroy := []string{}
	for _, h := range hypers {
		switch h.Status {
		case isardvdi.HypervisorStatusOnline:
			// Ensure we don't play with buffering hypervisors or non orchestrator managed ones! :)
			if !h.Buffering && h.OrchestratorManaged && len(h.GPUs) != 0 {
				// Check if we need to kill the hypervisor (because it's time to kill it or it has 0 desktops started)
				if !h.DestroyTime.IsZero() && (h.DestroyTime.Before(time.Now()) || h.DesktopsStarted == 0 || h.BookingsEndTime.Before(time.Now())) {
					hypersToDestroy = append(hypersToDestroy, h.ID)
				}
			}
		}
	}

	deadRow := chamaleonBestHypersToDestroy(hypersAvail, totalUnits, bookings)
	if len(deadRow) != 0 {
		c.log.Info().Array("ids", log.NewModelStrArray(deadRow)).Object("total_units", log.NewModelMapStrInt(totalUnits)).Object("req_units", log.NewModelMapStrInt(reqHypersUnits)).Str("scaling", "down").Msg("set hypervisors to destroy")
		return nil, nil, nil, deadRow, nil
	}

	if len(hypersToDestroy) != 0 {
		c.log.Info().Array("ids", log.NewModelStrArray(hypersToDestroy)).Str("scaling", "down").Msg("destroy hypervisors")
		return nil, &operationsv1.DestroyHypervisorsRequest{
			Ids: hypersToDestroy,
		}, nil, nil, nil
	}

	return nil, nil, nil, nil, nil
}

func chamaleonMaximumBookings(times ...isardvdi.OrchestratorGPUBookingTime) isardvdi.OrchestratorGPUBookingTime {
	booking := isardvdi.OrchestratorGPUBookingTime{}

	for _, t := range times {
		if t.Units > booking.Units {
			booking.Units = t.Units
		}
	}

	return booking
}

func chamaleonIsSmaller(this []*operationsv1.ListHypervisorsResponseHypervisor, thanThis []*operationsv1.ListHypervisorsResponseHypervisor) bool {
	lists := [2][]*operationsv1.ListHypervisorsResponseHypervisor{this, thanThis}
	mem := [2]int{}
	for i, l := range lists {
		currMem := 0
		for _, h := range l {
			for _, g := range h.Gpus {
				for _, card := range chamaleonGPUProfiles {
					if card.Brand == g.Brand && card.Model == g.Model {
						for _, p := range card.Profiles {
							if p.Units == 1 {
								currMem += p.Memory
							}
						}
					}
				}
			}
		}

		mem[i] = currMem
	}

	return mem[0] < mem[1]
}

// TODO: THIS SHOULD TAKE INTO ACCOUNT DIFFERENT DESKTOPS / BOOKINGS AND ALL THIS STUFF
func chamaleonIsBigger(this []*isardvdi.OrchestratorHypervisor, thanThis []*isardvdi.OrchestratorHypervisor) bool {
	lists := [2][]*isardvdi.OrchestratorHypervisor{this, thanThis}
	mem := [2]int{}
	dktps := [2]int{}
	for i, l := range lists {
		currMem := 0
		currDktp := 0
		for _, h := range l {
			currDktp += h.DesktopsStarted
			for _, g := range h.GPUs {
				for _, card := range chamaleonGPUProfiles {
					if card.Brand == g.Brand && card.Model == g.Model {
						for _, p := range card.Profiles {
							if p.Units == 1 {
								currMem += p.Memory
							}
						}
					}
				}
			}
		}

		mem[i] = currMem
		dktps[i] = currDktp
	}

	if mem[0] == mem[1] {
		// Here we return the desktop that has LESS desktops as the bigger
		return dktps[0] < dktps[1]
	}

	return mem[0] > mem[1]
}

func chamaleonBestHypersToCreateIsardVDI(avail []*isardvdi.OrchestratorHypervisor, minUnits map[string]int) ([]string, error) {
	hypers := []*operationsv1.ListHypervisorsResponseHypervisor{}
	for _, h := range avail {
		gpus := []*operationsv1.HypervisorGPU{}
		for _, g := range h.GPUs {
			gpus = append(gpus, &operationsv1.HypervisorGPU{
				Brand: g.Brand,
				Model: g.Model,
			})
		}

		hypers = append(hypers, &operationsv1.ListHypervisorsResponseHypervisor{
			Id:    h.ID,
			Cpu:   int32(h.CPU.Total),
			Ram:   int32(h.RAM.Total),
			State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
			Gpus:  gpus,
		})
	}

	return chamaleonBestHypersToCreate(hypers, minUnits)
}

func chamaleonBestHypersToCreate(avail []*operationsv1.ListHypervisorsResponseHypervisor, minUnits map[string]int) ([]string, error) {
	var bestHypers []*operationsv1.ListHypervisorsResponseHypervisor
	biggestCombo := []*operationsv1.ListHypervisorsResponseHypervisor{}

	combos := combinations.All(avail)
combosLoop:
	for _, c := range combos {
		hasEnough := true
		comboUnits := map[string]int{}

		// Count all the units for each profile that the combo has
		for _, h := range c {

			// Ensure all the hypervisors are available to create
			if h.State != operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE {
				continue combosLoop
			}

			for _, g := range h.Gpus {
				for _, card := range chamaleonGPUProfiles {
					if card.Brand == g.Brand && card.Model == g.Model {
						for _, p := range card.Profiles {
							comboUnits[p.Profile] += p.Units
						}
					}
				}
			}
		}

		// Ensure the combination has enough units
		hasProfile := true
		for minProfile, minUnit := range minUnits {
			availUnits, ok := comboUnits[minProfile]
			if !ok {
				hasEnough = false
				hasProfile = false
			}

			if minUnit > availUnits {
				hasEnough = false
			}
		}

		if hasEnough {
			if bestHypers != nil {
				// If the current combination is smalelr than the previous one, use this instead!
				if chamaleonIsSmaller(c, bestHypers) {
					bestHypers = c
				}
			} else {
				bestHypers = c
			}
		}

		if hasProfile {
			if chamaleonIsSmaller(biggestCombo, c) {
				biggestCombo = c
			}
		}
	}

	// If there's not enough resources in all the available combination, pick the biggest combination
	if bestHypers == nil {
		// If still there's no hypervisors available, return the error
		if len(biggestCombo) == 0 {
			return nil, ErrNoHypervisorAvailable
		}

		bestHypers = biggestCombo
	}

	ids := []string{}
	for _, h := range bestHypers {
		ids = append(ids, h.Id)
	}

	return ids, nil
}

func chamaleonCanBeDestroyed(hypers []*isardvdi.OrchestratorHypervisor, total map[string]int, bookings []*isardvdi.OrchestratorGPUBooking) bool {
	hypersUnits := map[string]int{}
	for _, h := range hypers {
		for _, g := range h.GPUs {
			hypersUnits[g.Profile] += g.TotalUnits
		}
	}

	canBeDestroyed := true
	for _, b := range bookings {
		t := chamaleonMaximumBookings(b.Now, b.Destroy)

		if total[b.Profile]-hypersUnits[b.Profile] < t.Units {
			canBeDestroyed = false
		}
	}

	return canBeDestroyed
}

func chamaleonBestHypersToDestroy(avail []*isardvdi.OrchestratorHypervisor, total map[string]int, bookings []*isardvdi.OrchestratorGPUBooking) []string {
	var bestHypers []*isardvdi.OrchestratorHypervisor

	combos := combinations.All(avail)
	for _, c := range combos {
		if chamaleonCanBeDestroyed(c, total, bookings) {
			if chamaleonIsBigger(c, bestHypers) {
				bestHypers = c
			}
		}
	}

	ids := []string{}
	for _, h := range bestHypers {
		ids = append(ids, h.ID)
	}

	return ids
}

func (c *Chamaleon) ExtraOperations(ctx context.Context, hypers []*isardvdi.OrchestratorHypervisor) error {
	return nil
}

/*
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$:.+~?rzXnr[I>$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$!?1u)||j?1Ur1v)nj|~$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$^_1X|urnr(10rZxr|c{vXnc$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$;_n/j1cfzrmqvxZOnLvmX|(/U(>$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ ucf(vrcmQquQ0tLCLYUOUx0cuQnvf $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$xnjt_/1fmtCOCYnCrnOmmXZncOZnmnOx{$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$-t1>$$$$$/J1UnxvUcuCuzL0LQnjXcrU0XLzQ0LupXmz$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$1w|c}CYXt$`fvjuJuYufvjuYCJJLU/CzJ0c|0ZqZqYCXUYp)$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$n1Qf1++{llz_Ccnc(JLfunxQznvJ|Ljqu|OZYCwwUpkzCmYOzZI$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$ncY<+_||ujftUvvUUQwzuLuxjOXu{XY/cXYzQ1O000w{QwXZQUOwv.$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$-O$QCt)})|r}1}Z<ZLuvYuUXctUY|cJuLQULnvzQ0xxumqkpJqr/?u/Jwn$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$YBrmd#)_xfcrr?nmzdzCJmYtUQfvvCQzuUYwC/LYzjXJxoqvCk|m-?{XfnxJC$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$M{iLvdOwOvr?f{u[z}oJCuQZuJzxcxUjYzCOYUzntnY/bwOUwzbU}t?rYQzXuvU$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$t*f)nukd(~rt(jj18nMXuuXJfuCttxuUc0JmudfL|xwmJLwvJ#mLU?_|jOxY|zvX^$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$iu_)L(<mWC/|vJ0onu)bOncQY{Q/fJnbuU0L0mCrCvzC)YUL**h*CJit}{ztw)tOrQ$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$<}?fXbJ$pBnCxccurnUdQwz+}]jCUXnCXxUJv(QLnC/mxCkWbQzLhoC!/v{fwOUvCXYm$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$+?f</vZC0Bb*))]{wzuJ*!~x/XLmUrY/rfrYnQ0YhCX{rfZz#cqQpkJr-(?ka)U0|zuYU]$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$!I|]-i|*88#Z1]f|vaUr@|xuYXYwnc0}rpUcJrCZOruY0OruapmunY#*u{nv0mYuZQUuuzJ$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$>~-<lI~l]zfJrf/x0wxb8djv0OZJYuunu)uzXunamwjLvjQufwO*z;pman1)xnLfY0quL/zXc$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$1[?~}+~>1,:1YrYcuZUcxLtZCmt0U1UZ0/+cXamBJZ`OtMQvqzYCq%h%0C-[tYp[0LQvzu}utL$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$t}>+{+<}|]; _mLJ*mcnz}v&kbXJxJQ]w)uci*B^>l&JX#0#j#p*#k%zo-f[tmtjULYr?c/fO-$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$/xrufnmXmaOcvQxcbcLC|XU*JOj(cOjk';j?n<8QBonBh8%*bOo#WvkY[ttxWx?vXzz)zvff)i$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$'l1}t(YC?)Zn/[XQ|f[[]jcmx0joXqk?+pnm/B&#&mWhm@%a/oLhbwbJ}_[z$tt)mrnnut)r(~!$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$ 'j![_|Qw(Y<{wzJOqcf(|Ymt)~l;i!_~WcLC8paBm&#&8MuwOdqndLL<t/X80|(fJnvj|Yt_+~!$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$n'+}I}_<ZnUQwbYY[//tn/rz[vx1}}{]|jvoB0Bd%mdoJChv0C(dCLn1}}wM*xcvvn(1z1xt?~+-$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$`II!Unz+Ukmxx(r((|YYcq}C|c(Cv]jz~jod%bWZkZZpQXfU}QfcvU<{rU*muvYwf)1Y1<~~Juf[$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$']inJfx?r(1}fzu(Xu#*wJx|mctvj!)UoMwdpfOYjOLZLLUUXXp>[|+nnvYLLYMZaabqZoruv0Ujti$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$  fQCX1)J/t[(/vQrCOmpbp#z??n/*w*UbqCbJwbZYQ]^^M}-]/-[hkZpQpLZL/wC01-~>([i]!{{jJmOQz!$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$^:"tzfvvXJ/00)L(XJbvw{]v)OapmLvcu(vYc1$;.:[xa__~+>prbUkhY*QMZ88dC0OdYYCJjv(dWZZt|t/zXc[$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$,$~i[>:i/:r<.$$?$$~]x|z$$$$$$$$$$$$$$+(!{Bk!;~?f&MO#M&%BB8MM%%qCY$@hOQmppk%amQuxr}<>]){j
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$Jd$$$$$$$!_?xz$$$$$$$$$$$$dpqQm0Lw]<((~Z*BMo#am,$$$$Ua*&%BB%B%@%B@#WCunpZZYXj1?
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$xvQ$$$$$$_l?|$$$$$$$$$]a#vmnUXX#aoo{|1xUX$$$$$$$$$$$$uQwqha8&$$$vdhW%#@#adO{nvJ
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$[1C$$$$$~l-uO$$$$$$$o*zwCYCmqbhaXBaz1c1$$$$$$$$$$$$$$$XqZOQa8%$$$$$$$uw##*M*hUw
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$(~vu$$$$_}(C$$$$$$&*wmOrYd#aB*J_I<$$$0Q$$$$$$$$$$$$$$$$XhmXqMW.$$$$$$$$$$/ppdbJ
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$+~}0$$$<l~Qq$$$$Q8`.cUb&&8*d1v>jJQ$$$$$$$$$$$$$$$$$$$$$$pJCvYOW$$$$$$$$$$$$$$1Z
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$!_x$$$`--j$$$$kq[xuLhB%Z$$$$$pL$$$$$$$$$$$$$$$$$$$$$$$$${r/cvv.$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$-it$$l/|tt$$w*(CddbZdpbc$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$<-]uxO$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$::<O'"+LO$|amJOoWBMWhz$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$${[|_xj$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$,.~o{?(z$awLQbMa#k$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$!?/j(n$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$:.'1:-/fc&jzzOk8*$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$+!?tup$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$. ,L;">`bjQw*%MX$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$":~rq$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$`.`}U:;+^On*kah$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$;}I/X $$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$].'>O$_:;>Qw&o$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$<<+fv]$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$'.Ix$$__:j%80$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$_>}Yd$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$`'`}0jCYi}(a$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$,~1Xh$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$''>xdvmX[;}Q$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$i_}ta$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$',I/#hUOqo<1v$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$,":~?]$$$$$$"-}[a$$$$$$$$$$$$$
}{xruxt$$$$$$$$$$$$$$$$$$$$$$$$$$':<QkO0*&dtmq$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$b!)i[(#_u$$$$<]xuU$$$$$$$$$$$$$
{tnzjnunYQJnzJUzx $<X$$$$$$`>;$$'`OaJUCaMq$$J$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$+!(zok8Jr]$$$$>+?u.$$$$$$$$$$$$$
xcuuuxfUX/}CYOm0YpuxO|}$$$I"[]>'JkkkQqdkC$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$IIuM+u1U-vt$$'[)|U$$$$$$$$$$$$$$
(ujJLXL1J0cJCvUmdm)-<Odj><(?nqm*UC0wd&#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$+1iL{O%pxC]z$$^_r1O$$$$$$$$$$$$$$
$$$$^fzCZYqpYdbbapZnCLr}mq8twd0QLb*p*b$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$z[>a|&J$|a_u$$dnjZ]$$$$$$$$$$$$$$
$$$$$$$$$$$-tOwbadtMdpmZJp#a0XbQo*bM$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$r{1JUO/~U:rX$`vtLZ$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$ Jdbababq*dWWapqm$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$u/tzLxjCU_jh`#?Lwj$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$xOkka*#*wv$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$_tuuvv(xcm,_n(X#$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$;:>-xY$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$f)jX|C0w~I|)jUC^$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$nf"Y?$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$xutC]/((jffjZO$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$id$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$_ZczXfUJffYc^$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$&YzkLLUCL'$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$M#W%*$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
*/
