package migrations

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"gitlab.com/isard/isardvdi/pkg/cfg"
	orchestrator "gitlab.com/isard/isardvdi/pkg/proto/orchestrator/v1"

	"github.com/hibiken/asynq"
	"libvirt.org/go/libvirt"
)

type Interface interface {
	MigrateHypervisor(ctx context.Context, hypervisor string) error
}

type Migrations struct {
	orchestrator orchestrator.OrchestratorServiceClient
	asynqClient  *asynq.Client
	asynqServer  *asynq.Server
}

func (m *Migrations) Close() error {
	m.asynqServer.Stop()
	m.asynqServer.Shutdown()

	return m.asynqClient.Close()
}

const (
	QueueCritical       = "critical"
	QueueCriticalWeight = 6
	QueueDefault        = "default"
	QueueDefaultWeight  = 3
	QueueLow            = "low"
	QueueLowWeight      = 1
)

// TODO: Logger, on error
func NewMigrations(r cfg.Redis) *Migrations {
	asynqClient := asynq.NewClient(asynq.RedisClientOpt{
		Addr:     r.Addr(),
		Username: r.Usr,
		Password: r.Pwd,
	})

	asynqServer := asynq.NewServer(asynq.RedisClientOpt{
		Addr:     r.Addr(),
		Username: r.Usr,
		Password: r.Pwd,
	}, asynq.Config{
		Queues: map[string]int{
			QueueCritical: QueueCriticalWeight,
			QueueDefault:  QueueDefaultWeight,
			QueueLow:      QueueLowWeight,
		},
	})

	m := &Migrations{
		asynqClient: asynqClient,
		asynqServer: asynqServer,
	}

	mux := asynq.NewServeMux()
	mux.HandleFunc(TaskMigrateDesktop, m.HandleDesktopMigration)

	if err := asynqServer.Start(asynq.NewServeMux()); err != nil {
		panic(err)
	}

	return m
}

type MigrationTask struct {
	DesktopID        string
	SourceHyper      string
	DestinationHyper string
}

const (
	TaskMigrateDesktop = "desktop:migrate"
)

func (m *Migrations) MigrateHypervisor(ctx context.Context, hypervisor string) error {
	conn, err := libvirt.NewConnect(hypervisor)
	if err != nil {
		return fmt.Errorf("connect to the libvirt daemon: %w", err)
	}

	doms, err := conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
	if err != nil {
		return fmt.Errorf("list all hypervisor domains: %w", err)
	}

	rsp, err := m.orchestrator.GetHyper(ctx, &orchestrator.GetHyperRequest{})
	if err != nil {
		return fmt.Errorf("get hypervisors to migrate to: %w", err)
	}

	for i, dom := range doms {
		id, err := dom.GetName()
		if err != nil {
			panic(err)
		}

		b, err := json.Marshal(&MigrationTask{
			DesktopID:        id,
			SourceHyper:      hypervisor,
			DestinationHyper: rsp.Host[i],
		})
		if err != nil {
			panic(err)
		}

		info, err := m.asynqClient.Enqueue(asynq.NewTask(TaskMigrateDesktop, b))
		if err != nil {
			return fmt.Errorf("enqueue migration task: %w", err)
		}

		log.Println(info.ID)
	}

	return nil
}

func (m *Migrations) HandleDesktopMigration(ctx context.Context, task *asynq.Task) error {
	var migration MigrationTask
	if err := json.Unmarshal(task.Payload(), &migration); err != nil {
		panic(err)
	}

	src, err := libvirt.NewConnect(migration.SourceHyper)
	if err != nil {
		panic(err)
	}

	dst, err := libvirt.NewConnect(migration.DestinationHyper)
	if err != nil {
		panic(err)
	}

	dom, err := src.LookupDomainByName(migration.DesktopID)
	if err != nil {
		panic(err)
	}

	newDom, err := dom.Migrate3(dst, &libvirt.DomainMigrateParameters{}, libvirt.MIGRATE_LIVE)
	if err != nil {
		panic(err)
	}

	dom.Free()
	newDom.Free()

	return nil
}
