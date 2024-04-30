package http

import (
	"context"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/collector"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors/version"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"
)

type StatsServer struct {
	Addr       string
	Collectors []collector.Collector

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func (s *StatsServer) Serve(ctx context.Context, log *zerolog.Logger) {
	r := prometheus.NewRegistry()
	r.MustRegister(version.NewCollector("isardvdi_stats"))
	for _, c := range s.Collectors {
		r.MustRegister(c)
	}

	m := http.NewServeMux()
	m.HandleFunc("/metrics", func(w http.ResponseWriter, rq *http.Request) {
		start := time.Now()

		promhttp.HandlerFor(prometheus.Gatherers{r}, promhttp.HandlerOpts{
			ErrorHandling:       promhttp.ContinueOnError,
			MaxRequestsInFlight: 40,
		}).ServeHTTP(w, rq)

		log.Info().Dur("duration", time.Since(start)).Msg("stats served")
	})

	srv := http.Server{
		Addr:    s.Addr,
		Handler: m,
	}

	go func() {
		if err := srv.ListenAndServe(); err != nil {
			s.Log.Fatal().Err(err).Str("addr", s.Addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	srv.Shutdown(timeout)
	s.WG.Done()
}
