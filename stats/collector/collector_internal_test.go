package collector

import (
	"bytes"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

type fakeCollector struct {
	name  string
	desc  *prometheus.Desc
	panic bool
}

func (f *fakeCollector) Describe(ch chan<- *prometheus.Desc) { ch <- f.desc }

func (f *fakeCollector) Collect(ch chan<- prometheus.Metric) {
	if f.panic {
		var p *struct{ v int }
		_ = p.v
	}

	ch <- prometheus.MustNewConstMetric(f.desc, prometheus.GaugeValue, 1)
}

func (f *fakeCollector) String() string { return f.name }

func TestRecoveringKeepsTheOtherCollectors(t *testing.T) {
	assert := assert.New(t)

	var buf bytes.Buffer
	log := zerolog.New(&buf)

	broken := &fakeCollector{name: "broken", desc: prometheus.NewDesc("broken_up", "", nil, nil), panic: true}
	healthy := &fakeCollector{name: "healthy", desc: prometheus.NewDesc("healthy_up", "", nil, nil)}

	r := prometheus.NewRegistry()
	r.MustRegister(Recovering(broken, &log))
	r.MustRegister(Recovering(healthy, &log))

	mfs, err := r.Gather()
	assert.NoError(err)

	names := []string{}
	for _, mf := range mfs {
		names = append(names, mf.GetName())
	}
	assert.Equal([]string{"healthy_up"}, names)

	assert.Contains(buf.String(), `"collector":"broken"`)
	assert.Contains(buf.String(), "recovered from panic while collecting")
}
