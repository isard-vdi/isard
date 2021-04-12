package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *mutationResolver) Login(ctx context.Context, input model.LoginInput) (*model.LoginPayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) DesktopStart(ctx context.Context, id string) (*model.DesktopStartPayload, error) {
	panic(fmt.Errorf("not implemented"))
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
	panic(fmt.Errorf("not implemented"))
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
