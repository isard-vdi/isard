package http

import (
	"context"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/backend/graph"
	"gitlab.com/isard/isardvdi/backend/graph/generated"

	"github.com/99designs/gqlgen/graphql/handler"
	"github.com/99designs/gqlgen/graphql/playground"
	"github.com/rs/zerolog"
)

type BackendServer struct {
	Addr string

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func (b *BackendServer) Serve(ctx context.Context) {
	srv := handler.NewDefaultServer(generated.NewExecutableSchema(generated.Config{Resolvers: &graph.Resolver{}}))

	m := http.NewServeMux()
	m.Handle("/", playground.Handler("GraphQL playground", "/graphql"))
	m.Handle("/graphql", srv)

	s := http.Server{
		Addr:    b.Addr,
		Handler: m,
	}

	b.Log.Info().Str("addr", b.Addr).Msg("serving GraphQL through http")

	go func() {
		if err := s.ListenAndServe(); err != nil {
			b.Log.Fatal().Err(err).Str("addr", b.Addr).Msg("serve gRPC")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	b.WG.Done()
}
