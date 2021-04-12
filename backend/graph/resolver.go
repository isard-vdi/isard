package graph

//go:generate go run github.com/99designs/gqlgen

import (
	protoAuth "gitlab.com/isard/isardvdi/pkg/proto/auth"
	protoController "gitlab.com/isard/isardvdi/pkg/proto/controller"
	protoDiskOperations "gitlab.com/isard/isardvdi/pkg/proto/diskoperations"

	"github.com/go-pg/pg/v10"
)

// This file will not be regenerated automatically.
//
// It serves as dependency injection for your app, add any dependencies you require here.

type Resolver struct {
	Controller     protoController.ControllerClient
	Auth           protoAuth.AuthClient
	DiskOperations protoDiskOperations.DiskOperationsClient
	DB             *pg.DB
}
