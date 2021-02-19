package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/auth/authentication"

	"github.com/rs/zerolog"
)

type AuthServer struct {
	Authentication *authentication.Authentication
	Addr           string

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

type webhookResponse struct {
	UserID       string `json:"X-Hasura-User-Id,omitempty"`
	Role         string `json:"X-Hasura-Role,omitempty"`
	CacheControl string `json:"Cache-Control,omitempty"`
}

func (a *AuthServer) Serve(ctx context.Context) {
	a.Log.Info().Str("addr", a.Addr).Msg("serving auth through http")

	m := http.NewServeMux()
	m.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "Hasura Authentication is working :)")
	})
	m.HandleFunc("/webhook", func(w http.ResponseWriter, r *http.Request) {
		h := r.Header.Get("Authorization")

		id, err := a.Authentication.Check(r.Context(), h)
		if err != nil {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		rsp := &webhookResponse{
			UserID: id,
			// TODO: Check role
			Role: "admin",
			// TODO: Check expiration time
			CacheControl: "max-age=3600",
		}

		b, err := json.Marshal(rsp)
		if err != nil {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		w.Write(b)
		w.WriteHeader(http.StatusOK)
	})

	s := http.Server{
		Addr:    a.Addr,
		Handler: m,
	}

	go func() {
		if err := s.ListenAndServe(); err != nil {
			a.Log.Fatal().Err(err).Str("addr", a.Addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	a.WG.Done()
}
