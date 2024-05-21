package grpc

import (
	"context"
	"time"

	"github.com/rs/zerolog"
	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func protoToJSON(e *zerolog.Event, msg any, field string) *zerolog.Event {
	pb, ok := msg.(proto.Message)
	if !ok {
		return e.Dict(field, zerolog.Dict())
	}

	json, err := protojson.MarshalOptions{
		UseProtoNames: true,
	}.Marshal(pb)
	if err != nil {
		return e.Dict(field, zerolog.Dict())
	}

	return e.RawJSON(field, json)
}

// TODO: add metadata in debug level
// TODO: duration unit (also in authentication)
func newUnaryInterceptorLogger(log *zerolog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {

		start := time.Now()
		rsp, err := handler(ctx, req)
		end := time.Now()

		var e *zerolog.Event
		if err != nil {
			e = log.Error()

			s, ok := status.FromError(err)
			if !ok {
				e = e.Err(err)

			} else {
				e = e.Str("status", s.Code().String()).
					Str("err", s.Message()).
					Any("err_details", s.Details())
			}

		} else {
			e = log.Info()
		}

		e.Str("path", info.FullMethod).
			Dur("duration", end.Sub(start))

		e = protoToJSON(e, req, "data")
		e = protoToJSON(e, rsp, "response")

		e.Msg("response served")

		return rsp, err
	}
}
