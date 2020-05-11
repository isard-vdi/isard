package grpc_test

import (
	"context"
	"testing"

	"github.com/isard-vdi/isard/engine/pkg/proto"
	"github.com/isard-vdi/isard/engine/transport/grpc"

	"github.com/stretchr/testify/suite"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type TestDesktopSuite struct {
	suite.Suite
}

func TestDesktop(t *testing.T) {
	suite.Run(t, &TestDesktopSuite{})
}

func (s *TestDesktopSuite) TestDesktopStop() {
	e := &grpc.EngineServer{}
	ctx := context.Background()

	rsp, err := e.DesktopStop(ctx, &proto.DesktopStopRequest{})

	s.Equal(status.Error(codes.Unimplemented, "not implemented yet"), err)
	s.Nil(rsp)
}
