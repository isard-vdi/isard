package graph

import (
	"context"

	"github.com/99designs/gqlgen/graphql"
	"gitlab.com/isard/isardvdi/backend/graph/model"
)

type Directive struct {
	HasRole func(ctx context.Context, obj interface{}, next graphql.Resolver, role model.Role) (interface{}, error)
}

func NewDirective() Directive {
	return Directive{
		HasRole: func(ctx context.Context, obj interface{}, next graphql.Resolver, role model.Role) (interface{}, error) {
			// TODO: Authorization
			return next(ctx)
		},
	}
}
