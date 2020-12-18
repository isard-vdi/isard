package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"
	"net/url"

	authProv "gitlab.com/isard/isardvdi/backend/auth/provider"
	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/middleware"
	"gitlab.com/isard/isardvdi/backend/graph/model"
	"gitlab.com/isard/isardvdi/controller/pkg/proto"
)

func (r *mutationResolver) Login(ctx context.Context, provider string, organization string, usr *string, pwd *string) (*string, error) {
	h := middleware.GetHTTP(ctx)
	p := authProv.FromString(provider, r.Auth.Store, r.Auth.DB)

	form := url.Values{}
	form.Set("provider", p.String())
	form.Set("organization", organization)

	if usr != nil {
		form.Set("usr", *usr)
	}

	if pwd != nil {
		form.Set("pwd", *pwd)
	}

	h.R.Form = form

	if err := p.Login(*h.W, h.R); err != nil {
		return nil, err
	}

	// TODO: return user id
	return nil, nil
}

func (r *mutationResolver) DesktopStart(ctx context.Context, id string) (*model.Viewer, error) {
	_, err := r.controller.DesktopStart(ctx, &proto.DesktopStartRequest{Id: id})
	if err != nil {
		return nil, fmt.Errorf("desktop start: %w", err)
	}

	panic("not implemented")

	return nil, nil
}

func (r *mutationResolver) DesktopStop(ctx context.Context, id string) (*bool, error) {
	panic(fmt.Errorf("not implemented"))
}

// Mutation returns generated.MutationResolver implementation.
func (r *Resolver) Mutation() generated.MutationResolver { return &mutationResolver{r} }

type mutationResolver struct{ *Resolver }
