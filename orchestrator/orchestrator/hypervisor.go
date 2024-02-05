package orchestrator

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/orchestrator/log"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/jwt"
)

func (o *Orchestrator) createHypervisors(ctx context.Context, req *operationsv1.CreateHypervisorsRequest) {
	o.scaleMux.Lock()
	defer o.scaleMux.Unlock()

	o.wg.Add(1)
	defer o.wg.Done()

	o.scaling = true
	defer func() {
		o.scaling = false
	}()

	if err := o.openBufferingHypervisor(ctx); err != nil {
		o.log.Error().Err(err).Msg("open buffering hypervisors")
	}

	stream, err := o.operationsCli.CreateHypervisors(ctx, req)
	if err != nil {
		o.log.Error().Err(err).Msg("create hypervisors request stream")
		return
	}

hyperCreate:
	for {
		select {
		case <-ctx.Done():
			o.log.Error().Array("ids", log.NewModelStrArray(req.Ids)).Err(ErrTimeout).Msg("wait for the hypervisors to be created")
			return

		default:
			rsp, err := stream.Recv()
			if err != nil {
				if errors.Is(err, io.EOF) {
					break hyperCreate
				}

				o.log.Error().Array("ids", log.NewModelStrArray(req.Ids)).Err(err).Msg("create hypervisors")
				return
			}

			if rsp.State == operationsv1.OperationState_OPERATION_STATE_FAILED {
				o.log.Error().Array("ids", log.NewModelStrArray(req.Ids)).Err(errors.New(rsp.Msg)).Msg("create hypervisors failed")
				return
			}

			o.log.Debug().Array("ids", log.NewModelStrArray(req.Ids)).Str("state", rsp.State.String()).Str("msg", rsp.Msg).Msg("create hypervisors update recieved")
		}
	}

	o.log.Debug().Array("ids", log.NewModelStrArray(req.Ids)).Msg("hypervisors created")

	// Wait for the hypervisors to be online
	var wg sync.WaitGroup
	var created = make(chan string, len(req.Ids))
	var failed = make(chan string, len(req.Ids))

	for _, id := range req.Ids {
		wg.Add(1)

		go func(id string) {
			defer wg.Done()
			h := &isardvdi.OrchestratorHypervisor{ID: id}

		hyperOnline:
			for {
				select {
				case <-ctx.Done():
					o.log.Error().Str("id", id).Err(ErrTimeout).Msg("wait for the hypervisor to be online")
					failed <- id
					return

				default:
					h, err = o.apiCli.OrchestratorHypervisorGet(ctx, id)
					if err != nil {
						if !errors.Is(err, isardvdi.ErrNotFound) {
							o.log.Error().Str("id", id).Err(err).Msg("load hypervisor from DB")
							failed <- id
							return
						}

					} else {
						if h.Status == isardvdi.HypervisorStatusOnline {
							break hyperOnline
						}
					}

					time.Sleep(5 * time.Second)
				}
			}

			o.log.Debug().Str("id", id).Msg("hypervisor online")

			if o.checkCfg.Enabled {
				tkn, err := jwt.SignAPIJWT(o.apiSecret)
				if err != nil {
					o.log.Error().Str("id", h.ID).Str("status", string(h.Status)).Err(err).Msg("sign the JWT token for the hypervisor check")
					failed <- id
					return
				}

				if _, err := o.checkCli.CheckHypervisor(ctx, &checkv1.CheckHypervisorRequest{
					Host: o.apiAddress, // TODO: CHECK THIS HOST!!!?
					Auth: &checkv1.Auth{
						Method: &checkv1.Auth_Token{
							Token: &checkv1.AuthToken{
								Token: tkn,
							},
						},
					},
					HypervisorId:        id,
					TemplateId:          o.checkCfg.TemplateID,
					FailMaintenanceMode: o.checkCfg.FailMaintenanceMode,
					FailSelfSigned:      o.checkCfg.FailSelfSigned,
				}); err != nil {
					o.log.Error().Str("id", h.ID).Str("status", string(h.Status)).Err(err).Msg("run the hypervisor check")
					failed <- id
					return
				}

				o.log.Debug().Str("id", id).Msg("hypervisor check success")
			}

			if err := o.apiCli.OrchestratorHypervisorManage(ctx, h.ID); err != nil {
				o.log.Error().Str("id", h.ID).Str("status", string(h.Status)).Err(err).Msg("mark the hypervisor as managed by the orchestrator")
				failed <- id
				return
			}

			created <- id
		}(id)
	}

	wg.Wait()
	close(created)
	close(failed)

	idsCreated := []string{}
	for id := range created {
		idsCreated = append(idsCreated, id)
	}

	idsFailed := []string{}
	for id := range failed {
		idsFailed = append(idsFailed, id)
	}

	o.log.Info().Array("ids", log.NewModelStrArray(idsCreated)).Msg("hypervisors started")
	if len(idsFailed) != 0 {
		o.log.Info().Array("ids", log.NewModelStrArray(idsFailed)).Msg("hypervisor creations failed")
	}

	if err := o.closeBufferingHypervisor(ctx); err != nil {
		o.log.Error().Err(err).Msg("close buffering hypervisors")
	}
}

func (o *Orchestrator) destroyHypervisors(ctx context.Context, req *operationsv1.DestroyHypervisorsRequest) {
	o.scaleMux.Lock()
	defer o.scaleMux.Unlock()

	o.wg.Add(1)
	defer o.wg.Done()

	o.scaling = true
	defer func() {
		o.scaling = false
	}()

	for _, id := range req.Ids {
		if err := o.apiCli.OrchestratorHypervisorStopDesktops(ctx, id); err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("stop all the desktops in the hypervisor")
		}
	}

	stream, err := o.operationsCli.DestroyHypervisors(ctx, req)
	if err != nil {
		o.log.Error().Array("ids", log.NewModelStrArray(req.Ids)).Err(err).Msg("destroy hypervisors request stream")
		return
	}

	for {
		rsp, err := stream.Recv()
		if err != nil {
			if errors.Is(err, io.EOF) {
				break
			}

			o.log.Error().Array("ids", log.NewModelStrArray(req.Ids)).Err(err).Msg("destroy hypervisors")
			return
		}

		o.log.Debug().Array("ids", log.NewModelStrArray(req.Ids)).Str("state", rsp.State.String()).Str("msg", rsp.Msg).Msg("destroy hypervisors update recieved")
	}

	o.log.Info().Array("ids", log.NewModelStrArray(req.Ids)).Msg("hypervisors destroyed")
}

func (o *Orchestrator) removeHypervisorsFromDeadRow(ctx context.Context, ids []string) {
	o.scaleMux.Lock()
	defer o.scaleMux.Unlock()

	o.wg.Add(1)
	defer o.wg.Done()

	o.scaling = true
	defer func() {
		o.scaling = false
	}()

	for _, id := range ids {
		if err := o.apiCli.OrchestratorHypervisorRemoveFromDeadRow(ctx, id); err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("cancel hypervisor destruction")
			return
		}

		o.log.Info().Str("id", id).Msg("hypervisor destruction cancelled")
	}
}

func (o *Orchestrator) addHypervisorsToDeadRow(ctx context.Context, ids []string) {
	for _, id := range ids {
		destroyTime, err := o.apiCli.OrchestratorHypervisorAddToDeadRow(ctx, id)
		if err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("set hypervisor to destroy")
			return
		}

		o.log.Info().Str("id", id).Time("destroy_time", destroyTime).Msg("hypervisor destruction time scheduled")
	}
}

func (o *Orchestrator) bufferingHypervisorOperation(ctx context.Context, onlyForced bool) error {
	hypers, err := o.apiCli.HypervisorList(ctx)
	if err != nil {
		return fmt.Errorf("list hypervisors: %w", err)
	}

	for _, h := range hypers {
		if isardvdi.GetBool(h.Buffering) && isardvdi.GetBool(h.OnlyForced) != onlyForced {
			if err := o.apiCli.AdminHypervisorOnlyForced(ctx, isardvdi.GetString(h.ID), onlyForced); err != nil {
				return fmt.Errorf("set hypervisor only forced state '%t': %w", onlyForced, err)
			}
		}
	}

	return nil
}

func (o *Orchestrator) openBufferingHypervisor(ctx context.Context) error {
	if err := o.bufferingHypervisorOperation(ctx, false); err != nil {
		return fmt.Errorf("open buffering hypervisor: %w", err)
	}

	return nil
}

func (o *Orchestrator) closeBufferingHypervisor(ctx context.Context) error {
	if err := o.bufferingHypervisorOperation(ctx, true); err != nil {
		return fmt.Errorf("close buffering hypervisor: %w", err)
	}

	return nil
}
