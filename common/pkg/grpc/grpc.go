package grpc

import (
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// RequiredParams are the parameters that are required for a gRPC method
type RequiredParams map[string]interface{}

// Required returns an error if a parameter is required and it not provided
func Required(r RequiredParams) error {
	for k, v := range r {
		if v == nil {
			return status.Errorf(codes.InvalidArgument, "parameter %s is required and not provided", k)
		}
	}

	return nil
}
