package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"

	"github.com/99designs/gqlgen/graphql"
	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

func (r *queryResolver) Desktop(ctx context.Context) (*model.DesktopQueries, error) {
	// t := reflect.TypeOf(generated.DesktopQueriesResolver)

	// for i := 0; i < t.NumMethod(); i++ {
	// 	fmt.Println(t.Method(i).Name)
	// }
	// q := &model.DesktopQueries{}
	// preloads := GetPreloads(ctx)
	// fmt.Println(preloads)

	fields := graphql.CollectFieldsCtx(ctx, nil)
	for _, f := range fields {
		switch f.Name {
		case "get":
		}
	}
	panic(fmt.Errorf("not implemented"))
	return nil, nil
}

func (r *queryResolver) Template(ctx context.Context) (*model.TemplateQueries, error) {
	panic(fmt.Errorf("not implemented"))
}

// Query returns generated.QueryResolver implementation.
func (r *Resolver) Query() generated.QueryResolver { return &queryResolver{r} }

type queryResolver struct{ *Resolver }

// !!! WARNING !!!
// The code below was going to be deleted when updating resolvers. It has been copied here so you have
// one last chance to move it out of harms way if you want. There are two reasons this happens:
//  - When renaming or deleting a resolver the old code will be put in here. You can safely delete
//    it when you're done.
//  - You have helper methods in this file. Move them out to keep these resolver files clean.
func GetPreloads(ctx context.Context) []string {
	return GetNestedPreloads(
		graphql.GetOperationContext(ctx),
		graphql.CollectFieldsCtx(ctx, nil),
		"",
	)
}
func GetNestedPreloads(ctx *graphql.OperationContext, fields []graphql.CollectedField, prefix string) (preloads []string) {
	for _, column := range fields {
		for _, arg := range column.Arguments {
			fmt.Println(arg.Name)
			fmt.Println(arg.Value.Raw)
		}
		prefixColumn := GetPreloadString(prefix, column.Name)
		preloads = append(preloads, prefixColumn)
		preloads = append(preloads, GetNestedPreloads(ctx, graphql.CollectFields(ctx, column.Selections, nil), prefixColumn)...)
	}
	return
}
func GetPreloadString(prefix, name string) string {
	if len(prefix) > 0 {
		return prefix + "." + name
	}
	return name
}
