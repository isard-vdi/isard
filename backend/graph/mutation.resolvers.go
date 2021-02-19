package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
)

func (r *mutationResolver) Login(ctx context.Context, provider string, entityID string, usr *string, pwd *string) (*string, error) {
	u := ""
	if usr != nil {
		u = *usr
	}

	p := ""
	if pwd != nil {
		p = *pwd
	}

	// TODO: Redirect
	rsp, err := r.Auth.Login(ctx, &auth.LoginRequest{
		Provider: provider,
		EntityId: entityID,
		Usr:      u,
		Pwd:      p,
	})
	if err != nil {
		return nil, fmt.Errorf("login: %w", err)
	}

	return &rsp.Token, nil
}

func (r *mutationResolver) Desktop(ctx context.Context) (*model.DesktopMutations, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *mutationResolver) Template(ctx context.Context) (*model.TemplateMutations, error) {
	panic(fmt.Errorf("not implemented"))
}

// Mutation returns generated.MutationResolver implementation.
func (r *Resolver) Mutation() generated.MutationResolver { return &mutationResolver{r} }

type mutationResolver struct{ *Resolver }
