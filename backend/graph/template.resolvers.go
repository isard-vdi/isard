package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *templateMutationsResolver) Delete(ctx context.Context, obj *model.TemplateMutations, id string) (*model.TemplateDeletePayload, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *templateQueriesResolver) List(ctx context.Context, obj *model.TemplateQueries) ([]*model.Template, error) {
	panic(fmt.Errorf("not implemented"))
}

func (r *templateQueriesResolver) Get(ctx context.Context, obj *model.TemplateQueries, id string) (*model.Template, error) {
	panic(fmt.Errorf("not implemented"))
}

// TemplateMutations returns generated.TemplateMutationsResolver implementation.
func (r *Resolver) TemplateMutations() generated.TemplateMutationsResolver {
	return &templateMutationsResolver{r}
}

// TemplateQueries returns generated.TemplateQueriesResolver implementation.
func (r *Resolver) TemplateQueries() generated.TemplateQueriesResolver {
	return &templateQueriesResolver{r}
}

type templateMutationsResolver struct{ *Resolver }
type templateQueriesResolver struct{ *Resolver }
