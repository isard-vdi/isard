package collector

import (
	"fmt"
	"runtime/debug"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

const namespace = "isardvdi"

type Collector interface {
	Describe(chan<- *prometheus.Desc)
	Collect(chan<- prometheus.Metric)
	String() string
}

// Recovering wraps a collector so that a panic while collecting is logged
// and only that collector's scrape is cut short. The registry runs every
// Collect in its own goroutine, so without this a single nil dereference
// takes the whole stats process down and every metric of the host goes away.
func Recovering(c Collector, log *zerolog.Logger) Collector {
	return &recovering{Collector: c, log: log}
}

type recovering struct {
	Collector

	log *zerolog.Logger
}

func (r *recovering) Collect(ch chan<- prometheus.Metric) {
	defer func() {
		if rec := recover(); rec != nil {
			r.log.Error().Err(fmt.Errorf("%v", rec)).Str("collector", r.String()).Str("stack", string(debug.Stack())).Msg("recovered from panic while collecting")
		}
	}()

	r.Collector.Collect(ch)
}
