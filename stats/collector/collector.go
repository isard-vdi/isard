package collector

import (
	"github.com/prometheus/client_golang/prometheus"
)

const namespace = "isardvdi"

type Collector interface {
	Describe(chan<- *prometheus.Desc)
	Collect(chan<- prometheus.Metric)
	String() string
}
