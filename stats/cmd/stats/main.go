package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/stats/cfg"
	"gitlab.com/isard/isardvdi/stats/collector"

	influxdb2 "github.com/influxdata/influxdb-client-go/v2"
)

func main() {
	cfg := cfg.New()

	log := log.New("stats", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	collectors := map[string]collector.Collector{}
	if cfg.Collectors.Hypervisor.Enable {
		h, err := collector.NewHypervisor(&wg, cfg)
		if err != nil {
			log.Fatal().Err(err).Msg("initialize the hypervisors collector")
		}

		wg.Add(1)

		collectors[h.String()] = h
	}

	if cfg.Collectors.System.Enable {
		s := collector.NewSystem(cfg)
		collectors[s.String()] = s
	}

	enabledCollectors := []string{}
	for k := range collectors {
		enabledCollectors = append(enabledCollectors, k)
	}

	client := influxdb2.NewClient(fmt.Sprintf("http://%s:%d", cfg.InfluxDB.Host, cfg.InfluxDB.Port), cfg.InfluxDB.Token)
	defer client.Close()

	write := client.WriteAPIBlocking(cfg.InfluxDB.Org, cfg.InfluxDB.Bucket)

	go func() {
		for {
			for name, c := range collectors {
				p, err := c.Collect(ctx)
				if err != nil {
					log.Error().Err(err).Msgf("collect data from %s", name)
					continue
				}

				if err := write.WritePoint(ctx, p); err != nil {
					log.Error().Err(err).Msgf("insert data into InfluxDB from %s", name)
					continue
				}

				log.Info().Str("collector", name).Interface("point", &p).Msg("data sent")
			}
			time.Sleep(time.Second)
		}
	}()

	log.Info().Strs("collectors", enabledCollectors).Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()

	for _, c := range collectors {
		c.Close()
	}

	wg.Wait()
}
