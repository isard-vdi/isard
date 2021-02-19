package http

import (
	"context"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/backend/graph"
	"gitlab.com/isard/isardvdi/backend/graph/generated"
	"gitlab.com/isard/isardvdi/backend/graph/middleware"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"

	"github.com/99designs/gqlgen/graphql/handler"
	"github.com/99designs/gqlgen/graphql/handler/extension"
	"github.com/99designs/gqlgen/graphql/handler/lru"
	"github.com/99designs/gqlgen/graphql/handler/transport"
	"github.com/99designs/gqlgen/graphql/playground"
	"github.com/go-pg/pg/v10"
	"github.com/gorilla/websocket"
	"github.com/rs/zerolog"
	"google.golang.org/grpc"
)

type BackendServer struct {
	Addr string

	DB       *pg.DB
	AuthConn *grpc.ClientConn
	Auth     auth.AuthClient

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func (b *BackendServer) Serve(ctx context.Context) {
	srv := handler.New(generated.NewExecutableSchema(generated.Config{
		Resolvers: &graph.Resolver{Auth: b.Auth},
		// Directives: generated.DirectiveRoot(graph.NewDirective()),
	}))

	// Copied from NewDefaultServer(), but added the websocket transport
	srv.AddTransport(transport.Websocket{
		KeepAlivePingInterval: 10 * time.Second,
		Upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool {
				return true
			},
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
		},
	})
	srv.AddTransport(transport.Options{})
	srv.AddTransport(transport.GET{})
	srv.AddTransport(transport.POST{})
	srv.AddTransport(transport.MultipartForm{})

	srv.SetQueryCache(lru.New(1000))

	srv.Use(extension.Introspection{})
	srv.Use(extension.AutomaticPersistedQuery{
		Cache: lru.New(100),
	})

	middleware := middleware.NewMiddleware(b.DB, b.Auth)

	m := http.NewServeMux()
	m.Handle("/", playground.Handler("GraphQL playground", "/graphql"))
	m.Handle("/graphql", middleware.Serve(srv))

	s := http.Server{
		Addr:    b.Addr,
		Handler: m,
	}

	b.Log.Info().Str("addr", b.Addr).Msg("serving GraphQL through http")

	go func() {
		if err := s.ListenAndServe(); err != nil {
			b.Log.Fatal().Err(err).Str("addr", b.Addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	b.AuthConn.Close()
	b.WG.Done()
}
