package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"github.com/rs/xid"
	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/middleware"
	"gitlab.com/isard/isardvdi/backend/graph/model"
	"gitlab.com/isard/isardvdi/backend/viewer"
	cmnModel "gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
	"gitlab.com/isard/isardvdi/pkg/proto/controller"
	"gitlab.com/isard/isardvdi/pkg/proto/diskoperations"
)

// Login is used to authenticate the user
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

// DesktopStart starts a desktop
func (r *mutationResolver) DesktopStart(ctx context.Context, id string) (*model.DesktopStartPayload, error) {
	if err := middleware.IsAuthenticated(ctx); err != nil {
		return nil, err
	}

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

// DesktopCreate creates a new desktop from scratch
func (r *mutationResolver) DesktopCreate(ctx context.Context, input model.DesktopCreateInput) (*model.DesktopCreatePayload, error) {
	// TODO: Cleanup if there's an error
	// TOOD: Input sanitization
	if err := middleware.IsAuthenticated(ctx); err != nil {
		return nil, err
	}

	b := &cmnModel.HardwareBase{UUID: input.Hardware.BaseID}
	if err := b.LoadWithUUID(ctx, r.DB); err != nil {
		// TODO: Change this
		panic(err)
	}

	u, eID := middleware.AuthForContext(ctx)

	disks := []*cmnModel.Disk{}
	for _, d := range input.Hardware.Disks {
		if d.ID != nil {
			disk := &cmnModel.Disk{UUID: *d.ID}
			if err := disk.LoadWithUUID(ctx, r.DB); err != nil {
				panic(err)
			}

			disks = append(disks, disk)
		} else {
			rsp, err := r.DiskOperations.DiskCreate(ctx, &diskoperations.DiskCreateRequest{
				Type:        diskoperations.DiskType(diskType(*d.Type)),
				Size:        int32(*d.Size),
				EntityId:    int64(eID),
				UserId:      int64(u.ID),
				Name:        *d.Name,
				Description: *d.Description,
			})
			if err != nil {
				// TODO: ERR
				panic(err)
			}

			disks = append(disks, &cmnModel.Disk{ID: int(rsp.Id)})
		}
	}

	h := &cmnModel.Hardware{
		BaseID: b.ID,
		VCPUs:  input.Hardware.Vcpus,
		Memory: input.Hardware.Memory,
	}
	_, err := r.DB.Model(h).Returning("id").Insert()
	if err != nil {
		// TODO: Change this
		panic(err)
	}

	for _, d := range disks {
		if _, err := r.DB.ModelContext(ctx, &cmnModel.HardwareDisk{
			DiskID:     d.ID,
			HardwareID: h.ID,
			// TODO: Other disk parameters
		}).Insert(); err != nil {
			// TODO: Change this
			panic(err)
		}
	}

	d := &cmnModel.Desktop{
		Name:       input.Name,
		UUID:       xid.New().String(),
		HardwareID: h.ID,
		UserID:     u.ID,
		EntityID:   eID,
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

// diskType translates from GraphQL disk type to the common disk type
func diskType(d model.DiskType) cmnModel.DiskType {
	for i, disk := range model.AllDiskType {
		if d == disk {
			return cmnModel.DiskType(i)
		}
	}

	return cmnModel.DiskTypeUnknown
}
