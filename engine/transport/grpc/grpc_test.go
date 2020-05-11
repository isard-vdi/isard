package grpc_test

import (
	"context"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/isard-vdi/isard/engine/transport/grpc"
	"github.com/isard-vdi/isard/engine/utils/test"

	"github.com/stretchr/testify/suite"
)

type TestGRPCSuite struct {
	test.Test
}

func TestGRPC(t *testing.T) {
	suite.Run(t, &TestGRPCSuite{})
}

func (s *TestGRPCSuite) TestServe() {
	s.Run("should start the gRPC server correctly", func() {
		ctx, cancel := context.WithCancel(context.Background())

		env := s.PrepareEnv()

		go grpc.Serve(ctx, env)
		env.WG.Add(1)

		time.Sleep(1 * time.Second)

		cancel()
	})

	s.Run("should exit if there's an error listening to the port", func() {
		ctx := context.Background()

		env := s.PrepareEnv()

		lis, err := net.Listen("tcp", fmt.Sprintf(":%d", env.Cfg.GRPC.Port))
		s.Require().NoError(err)
		defer lis.Close()

		s.Exits(func() { grpc.Serve(ctx, env) })
	})
}
