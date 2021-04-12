package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/graph/generated"
	model1 "gitlab.com/isard/isardvdi/backend/graph/graph/model"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *viewerResolver) VncHTML(ctx context.Context, obj *model.Viewer) (*model1.ViewerVncHTML, error) {
	panic(fmt.Errorf("not implemented"))
}

// Viewer returns generated.ViewerResolver implementation.
func (r *Resolver) Viewer() generated.ViewerResolver { return &viewerResolver{r} }

type viewerResolver struct{ *Resolver }
