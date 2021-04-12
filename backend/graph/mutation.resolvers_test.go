package graph_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/backend/graph"
	"gitlab.com/isard/isardvdi/backend/graph/middleware"
	"gitlab.com/isard/isardvdi/backend/graph/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
)

func TestDesktopCreate(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	// diskType := model.DiskTypeQcow2

	cases := map[string]struct {
		PrepareTest     func(ctx context.Context, authMock *auth.AuthServiceMock) context.Context
		Input           *model.DesktopCreateInput
		ExpectedErr     string
		ExpectedPayload *model.DesktopCreatePayload
	}{
		// "should work as expected": {
		// 	PrepareTest: func(ctx context.Context, authMock *auth.AuthServiceMock) context.Context {
		// 		return middleware.SetAuthContext(ctx, &cmnModel.User{ID: 1}, 1)
		// 	},
		// 	Input: &model.DesktopCreateInput{
		// 		Name: "test",
		// 		Hardware: &model.DesktopCreateInputHardware{
		// 			BaseID: "uuid",
		// 			Vcpus:  2,
		// 			Memory: 2048,
		// 			Disks: []*model.DesktopCreateInputHardwareDisk{{
		// 				ID: pointer.ToString("uuid"),
		// 			}, {
		// 				Type:        &diskType,
		// 				Name:        pointer.ToString("disk"),
		// 				Description: pointer.ToString("description"),
		// 				Size:        pointer.ToInt(2048),
		// 			}},
		// 		},
		// 	},
		// },
		"should return an error if the user isn't authenticated": {
			ExpectedErr: middleware.ErrNotAuthenticated.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			authMock, authCli, err := auth.NewAuthServiceMock()
			require.NoError(err)

			r := &graph.Resolver{
				Auth: authCli,
			}

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			if tc.PrepareTest != nil {
				ctx = tc.PrepareTest(ctx, authMock)
			}

			input := tc.Input
			if input == nil {
				input = &model.DesktopCreateInput{}
			}
			payload, err := r.Mutation().DesktopCreate(ctx, *input)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedPayload, payload)
		})
	}
}
