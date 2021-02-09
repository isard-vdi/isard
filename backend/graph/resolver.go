//go:generate go run github.com/99designs/gqlgen

package graph

import (
	"gitlab.com/isard/isardvdi/backend/auth"
	"gitlab.com/isard/isardvdi/controller/pkg/proto"
	"google.golang.org/grpc"
)

// This file will not be regenerated automatically.
//
// It serves as dependency injection for your app, add any dependencies you require here.

type Resolver struct {
	controllerConn *grpc.ClientConn
	controller     proto.ControllerClient

	Auth *auth.Auth
}
