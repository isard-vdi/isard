package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"github.com/rs/xid"
	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
	"gitlab.com/isard/isardvdi/backend/viewer"
	cmnModel "gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
	"gitlab.com/isard/isardvdi/pkg/proto/controller"
)

func (r *mutationResolver) Login(ctx context.Context, input model.LoginInput) (*model.LoginPayload, error) {
	u := ""
	if input.Usr != nil {
		u = *input.Usr
	}

	p := ""
	if input.Pwd != nil {
		p = *input.Pwd
	}

	// TODO: Redirect
	rsp, err := r.Auth.Login(ctx, &auth.LoginRequest{
		Provider:   input.Provider,
		EntityUuid: input.EntityID,
		Usr:        u,
		Pwd:        p,
	})
	if err != nil {
		return nil, fmt.Errorf("login: %w", err)
	}

	return &model.LoginPayload{
		Token:   rsp.Token,
		ID:      rsp.Uuid,
		Name:    rsp.Name,
		Surname: rsp.Surname,
	}, nil
}

func (r *mutationResolver) DesktopStart(ctx context.Context, id string) (*model.DesktopStartPayload, error) {
	rsp, err := r.Controller.DesktopStart(ctx, &controller.DesktopStartRequest{
		Id: id,
	})
	if err != nil {
		// TODO: Change this
		panic(err)
	}

	v := &model.Viewer{}
	for _, s := range rsp.Viewer.Spice {
		v.Spice = &model.ViewerSpice{
			File: viewer.GenSpice(s.Host, int(s.TlsPort), s.Pwd),
		}
	}
	for range rsp.Viewer.Vnc {
		v.VncHTML = &model.ViewerVncHTML{
			URL: "TODO",
		}
	}

	return &model.DesktopStartPayload{
		RecordID: &id,
		Viewer:   v,
	}, nil
}

func (r *mutationResolver) DesktopStop(ctx context.Context, id string) (*model.DesktopStopPayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) DesktopDelete(ctx context.Context, id string) (*model.DesktopDeletePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) DesktopTemplate(ctx context.Context, input model.DesktopTemplateInput) (*model.DesktopTemplatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) DesktopCreate(ctx context.Context, input model.DesktopCreateInput) (*model.DesktopCreatePayload, error) {
	b := &cmnModel.HardwareBase{UUID: input.Hardware.BaseID}
	if err := b.LoadWithUUID(ctx, r.DB); err != nil {
		// TODO: Change this
		panic(err)
	}

	h := &cmnModel.Hardware{
		BaseID:    b.ID,
		VCPUs:     input.Hardware.Vcpus,
		MemoryMin: input.Hardware.MemoryMin,
		MemoryMax: input.Hardware.MemoryMax,
	}
	_, err := r.DB.Model(h).Returning("id").Insert()
	if err != nil {
		// TODO: Change this
		panic(err)
	}

	d := &cmnModel.Desktop{
		Name:       input.Name,
		UUID:       xid.New().String(),
		HardwareID: h.ID,
	}
	if input.Description != nil {
		d.Description = *input.Description
	}

	_, err = r.DB.Model(d).Insert()
	if err != nil {
		// TODO: Change this
		panic(err)
	}

	return &model.DesktopCreatePayload{
		RecordID: &d.UUID,
	}, nil
}

func (r *mutationResolver) DesktopDerivate(ctx context.Context, input model.DesktopDerivateInput) (*model.DesktopDerivatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) TemplateDelete(ctx context.Context, id string) (*model.TemplateDeletePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) HardwareBaseCreate(ctx context.Context, input model.HardwareBaseCreateInput) (*model.HardwareBaseCreatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

// Mutation returns generated.MutationResolver implementation.
func (r *Resolver) Mutation() generated.MutationResolver { return &mutationResolver{r} }

type mutationResolver struct{ *Resolver }
