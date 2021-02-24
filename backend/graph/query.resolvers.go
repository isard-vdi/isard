package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *queryResolver) DesktopList(ctx context.Context) ([]*model.Desktop, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) DesktopGet(ctx context.Context, id string) (*model.Desktop, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) DesktopViewer(ctx context.Context, id string) (*model.Viewer, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) TemplateList(ctx context.Context) ([]*model.Template, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) TemplateGet(ctx context.Context, id string) (*model.Template, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) HardwareBaseList(ctx context.Context) ([]*model.HardwareBase, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *queryResolver) HardwareBaseGet(ctx context.Context, id string) (*model.HardwareBase, error) {
	panic(fmt.Errorf("not implemented"))
}

// Query returns generated.QueryResolver implementation.
func (r *Resolver) Query() generated.QueryResolver { return &queryResolver{r} }

type queryResolver struct{ *Resolver }
