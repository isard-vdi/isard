//go:generate go run github.com/99designs/gqlgen

package graph

import (
	protoAuth "gitlab.com/isard/isardvdi/pkg/proto/auth"
	protoController "gitlab.com/isard/isardvdi/pkg/proto/controller"

	"github.com/go-pg/pg/v10"
)

// This file will not be regenerated automatically.
//
// It serves as dependency injection for your app, add any dependencies you require here.

type Resolver struct {
	Controller protoController.ControllerClient
	Auth       protoAuth.AuthClient
	DB         *pg.DB
}
