package orchestrator

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/log"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/jwt"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
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

		hyperOnline:
			for {
				select {
				case <-ctx.Done():
					o.log.Error().Str("id", id).Err(ErrTimeout).Msg("wait for the hypervisor to be online")
					failed <- id
					return

				default:
					res, err := o.apiCli.AdminOrchestratorHypervisorGet(ctx, apiv4.AdminOrchestratorHypervisorGetParams{
						HypervisorID: id,
					})
					if err != nil {
						o.log.Error().Str("id", id).Err(err).Msg("load hypervisor from DB")
						failed <- id
						return
					}

					if v, ok := res.(*apiv4.OrchestratorHypervisor); ok {
						h := model.NewHypervisor(v)
						if h.Status == model.HypervisorStatusOnline {
							// Hypervisor is online, run checks and manage it
							if o.checkCfg.Enabled {
								tkn, err := jwt.SignAPIJWT(o.apiSecret)
								if err != nil {
									o.log.Error().Str("id", h.ID).Str("status", h.Status).Err(err).Msg("sign the JWT token for the hypervisor check")
									failed <- id
									return
								}

								if _, err := o.checkCli.CheckHypervisor(ctx, &checkv1.CheckHypervisorRequest{
									Host: o.apiAddress,
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
									o.log.Error().Str("id", h.ID).Str("status", h.Status).Err(err).Msg("run the hypervisor check")
									failed <- id
									return
								}

								o.log.Debug().Str("id", id).Msg("hypervisor check success")
							}

							if err := o.orchestratorManageSet(ctx, h.ID); err != nil {
								o.log.Error().Str("id", h.ID).Str("status", h.Status).Err(err).Msg("mark the hypervisor as managed by the orchestrator")
								failed <- id
								return
							}

							created <- id
							break hyperOnline
						}

						time.Sleep(5 * time.Second)
						continue
					}

					apiErr := ogenclient.AsAPIError(res)
					if errors.Is(apiErr, ogenclient.ErrNotFound) {
						time.Sleep(5 * time.Second)
						continue
					}

					o.log.Error().Str("id", id).Err(apiErr).Msg("load hypervisor from DB")
					failed <- id
					return
				}
			}

			o.log.Debug().Str("id", id).Msg("hypervisor online")
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

func (o *Orchestrator) orchestratorManageSet(ctx context.Context, id string) error {
	res, err := o.apiCli.AdminOrchestratorManageSet(ctx, apiv4.AdminOrchestratorManageSetParams{
		HypervisorID: id,
	})
	if err != nil {
		return fmt.Errorf("manage set hypervisor %q: %w", id, err)
	}

	if _, ok := res.(*apiv4.AdminOrchestratorManageSetNoContent); ok {
		return nil
	}

	return ogenclient.AsAPIError(res)
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
		if err := o.orchestratorStopDesktops(ctx, id); err != nil {
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

func (o *Orchestrator) orchestratorStopDesktops(ctx context.Context, id string) error {
	res, err := o.apiCli.AdminOrchestratorStopDesktops(ctx, apiv4.AdminOrchestratorStopDesktopsParams{
		HypervisorID: id,
	})
	if err != nil {
		return fmt.Errorf("stop desktops on hypervisor %q: %w", id, err)
	}

	if _, ok := res.(*apiv4.AdminOrchestratorStopDesktopsNoContent); ok {
		return nil
	}

	return ogenclient.AsAPIError(res)
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
		if err := o.orchestratorDeadRowReset(ctx, id); err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("cancel hypervisor destruction")
			return
		}

		o.log.Info().Str("id", id).Msg("hypervisor destruction cancelled")
	}
}

func (o *Orchestrator) orchestratorDeadRowReset(ctx context.Context, id string) error {
	res, err := o.apiCli.AdminOrchestratorDeadRowReset(ctx, apiv4.AdminOrchestratorDeadRowResetParams{
		HypervisorID: id,
	})
	if err != nil {
		return fmt.Errorf("dead row reset hypervisor %q: %w", id, err)
	}

	if _, ok := res.(*apiv4.AdminOrchestratorDeadRowResetNoContent); ok {
		return nil
	}

	return ogenclient.AsAPIError(res)
}

func (o *Orchestrator) addHypervisorsToDeadRow(ctx context.Context, ids []string) {
	for _, id := range ids {
		destroyTime, err := o.orchestratorDeadRowSet(ctx, id)
		if err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("set hypervisor to destroy")
			return
		}

		o.log.Info().Str("id", id).Time("destroy_time", destroyTime).Msg("hypervisor destruction time scheduled")
	}
}

func (o *Orchestrator) orchestratorDeadRowSet(ctx context.Context, id string) (time.Time, error) {
	res, err := o.apiCli.AdminOrchestratorDeadRowSet(ctx, apiv4.AdminOrchestratorDeadRowSetParams{
		HypervisorID: id,
	})
	if err != nil {
		return time.Time{}, fmt.Errorf("dead row set hypervisor %q: %w", id, err)
	}

	if v, ok := res.(*apiv4.DeadRowSetResponse); ok {
		return v.DestroyTime, nil
	}

	return time.Time{}, ogenclient.AsAPIError(res)
}

func (o *Orchestrator) removeHypervisorsFromOnlyForced(ctx context.Context, ids []string) {
	o.scaleMux.Lock()
	defer o.scaleMux.Unlock()

	o.wg.Add(1)
	defer o.wg.Done()

	o.scaling = true
	defer func() {
		o.scaling = false
	}()

	for _, id := range ids {
		if err := o.adminHypervisorOnlyForced(ctx, id, false); err != nil {
			o.log.Error().Str("id", id).Err(err).Msg("unlimit hypervisor")
			return
		}

		o.log.Info().Str("id", id).Msg("hypervisor unlimited")
	}
}

func (o *Orchestrator) adminHypervisorOnlyForced(ctx context.Context, id string, onlyForced bool) error {
	body := apiv4.AdminTableUpdateReq{
		"id":          model.MustJxRaw(id),
		"only_forced": model.MustJxRaw(onlyForced),
	}

	res, err := o.apiCli.AdminTableUpdate(ctx, body, apiv4.AdminTableUpdateParams{
		Table: "hypervisors",
	})
	if err != nil {
		return fmt.Errorf("update hypervisor only_forced: %w", err)
	}

	if _, ok := res.(*apiv4.AdminTableUpdateNoContent); ok {
		return nil
	}

	return ogenclient.AsAPIError(res)
}

func (o *Orchestrator) bufferingHypervisorOperation(ctx context.Context, onlyForced bool) error {
	res, err := o.apiCli.AdminHypervisorsList(ctx, apiv4.AdminHypervisorsListParams{})
	if err != nil {
		return fmt.Errorf("list hypervisors: %w", err)
	}

	v, ok := res.(*apiv4.AdminHypervisorsListOKApplicationJSON)
	if !ok {
		return ogenclient.AsAPIError(res)
	}

	list := []apiv4.AdminHypervisor(*v)
	for i := range list {
		h := &list[i]
		if h.BufferingHyper && h.OnlyForced != onlyForced {
			if err := o.adminHypervisorOnlyForced(ctx, h.ID, onlyForced); err != nil {
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
