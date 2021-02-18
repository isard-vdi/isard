package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *desktopMutationsResolver) Start(ctx context.Context, obj *model.DesktopMutations, id string) (*model.DesktopStartPayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopMutationsResolver) Stop(ctx context.Context, obj *model.DesktopMutations, id string) (*model.DesktopStopPayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopMutationsResolver) Delete(ctx context.Context, obj *model.DesktopMutations, id string) (*model.DesktopDeletePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopMutationsResolver) Template(ctx context.Context, obj *model.DesktopMutations, input model.DesktopTemplateInput) (*model.DesktopTemplatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopMutationsResolver) Create(ctx context.Context, obj *model.DesktopMutations, input model.DesktopCreateInput) (*model.DesktopCreatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopMutationsResolver) Derivate(ctx context.Context, obj *model.DesktopMutations, input model.DesktopDerivateInput) (*model.DesktopDerivatePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopQueriesResolver) List(ctx context.Context, obj *model.DesktopQueries) ([]*model.Desktop, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopQueriesResolver) Get(ctx context.Context, obj *model.DesktopQueries, id string) (*model.Desktop, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *desktopQueriesResolver) Viewer(ctx context.Context, obj *model.DesktopQueries, id string) (*model.Viewer, error) {
	panic(fmt.Errorf("not implemented"))
}

// DesktopMutations returns generated.DesktopMutationsResolver implementation.
func (r *Resolver) DesktopMutations() generated.DesktopMutationsResolver {
	return &desktopMutationsResolver{r}
}

// DesktopQueries returns generated.DesktopQueriesResolver implementation.
func (r *Resolver) DesktopQueries() generated.DesktopQueriesResolver {
	return &desktopQueriesResolver{r}
}

type desktopMutationsResolver struct{ *Resolver }
type desktopQueriesResolver struct{ *Resolver }
