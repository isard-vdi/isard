package grpc_test

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/common/pkg/grpc"

	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestRequired(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Params      func() grpc.RequiredParams
		ExpectedErr string
	}{
		"shouldn't return an error if all the fields are provided": {
			Params: func() grpc.RequiredParams {
				id := "example"
				number := 0

				return grpc.RequiredParams{
					"id":      &id,
					"timeout": time.After(time.Hour),
					"number":  &number,
				}
			},
		},
		"should return a grpc status error if a required parameter isn't provided": {
			Params: func() grpc.RequiredParams {
				return grpc.RequiredParams{
					"id": nil,
				}
			},
			ExpectedErr: status.Error(codes.InvalidArgument, "parameter 'id' is required and not provided").Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			err := grpc.Required(tc.Params())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}
