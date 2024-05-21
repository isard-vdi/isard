package grpc

import (
	"context"
	"fmt"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewClient[T interface{}](ctx context.Context, newClient func(grpc.ClientConnInterface) T, addr string) (T, *grpc.ClientConn, error) {
	opts := []grpc.DialOption{
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	}
	cc, err := grpc.DialContext(ctx, addr, opts...)
	if err != nil {
		return newClient(cc), cc, fmt.Errorf("dial the gRPC service: %w", err)
	}

	return newClient(cc), cc, nil
}
