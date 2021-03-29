package hyper

import (
	"context"
	"errors"
	"fmt"
	"os"

	"gitlab.com/isard/isardvdi/pkg/pool"
	"gitlab.com/isard/isardvdi/pkg/state"

	"github.com/go-redis/redis/v8"
	"github.com/qmuntal/stateless"
	"libvirt.org/libvirt-go"
)

// Interface is an interface with all the actions that a hypervisor has to be able to do
type Interface interface {
	// Get returns a running desktop using it's name
	Get(name string) (*libvirt.Domain, error)

	// Start starts a new machine using the provided XML definition
	// It's a non-persistent desktop from libvirt point of view
	Start(xml string, options *StartOptions) (*libvirt.Domain, error)

	// Stop stops a running desktop
	Stop(desktop *libvirt.Domain) error

	// Suspend suspends a running desktop temporarily saving its memory state. It won't persist if the hypervisor restarts
	Suspend(desktop *libvirt.Domain) error

	// Resume resumes a suspended desktop to its original running state, continuing the execution where it was left
	Resume(desktop *libvirt.Domain) error

	// Save saves a running desktop saving its memory state to a file. It will persist if the hypervisor restarts
	Save(desktop *libvirt.Domain, path string) error

	// Restore restores a saved desktop to its original running state, continuing the execution where it was left
	Restore(path string) error

	// XMLGet returns the running XML definition of a desktop
	XMLGet(desktop *libvirt.Domain) (string, error)

	// List returns a list of all the running desktops
	List() ([]libvirt.Domain, error)

	// Migrate migrates a running desktop to another hypervisor using PEER2PEER method
	Migrate(desktop *libvirt.Domain, hyperURI string) error

	// Close closes the libvirt connection with the hypervisor
	Close(ctx context.Context) error
}

// Hyper is the implementation of the hyper Interface
type Hyper struct {
	conn *libvirt.Connect

	host       string
	domEventID int

	hypers   *pool.HyperPool
	desktops *pool.DesktopPool
}

func init() {
}

// New creates a new Hyper and connects to the libvirt daemon
func New(ctx context.Context, redis redis.UniversalClient, uri, host string) (*Hyper, error) {
	if uri == "" {
		uri = "qemu:///system"
	}

	if host == "" {
		var err error
		host, err = os.Hostname()
		if err != nil {
			return nil, fmt.Errorf("get hostname: %w", err)
		}
	}

	if err := libvirt.EventRegisterDefaultImpl(); err != nil {
		return nil, fmt.Errorf("register libvirt events: %w", err)
	}

	go func() {
		for {
			select {
			case <-ctx.Done():
				return

			default:
				if err := libvirt.EventRunDefaultImpl(); err != nil {
					panic(err)
				}
			}
		}
	}()

	conn, err := libvirt.NewConnect(uri)
	if err != nil {
		return nil, fmt.Errorf("connect to libvirt: %w", err)
	}

	h := &Hyper{
		conn: conn,
		host: host,

		hypers:   pool.NewHyperPool(ctx, redis),
		desktops: pool.NewDesktopPool(ctx, redis),
	}

	domEventID, err := conn.DomainEventLifecycleRegister(nil, func(c *libvirt.Connect, d *libvirt.Domain, event *libvirt.DomainEventLifecycle) {
		id, err := d.GetName()
		if err != nil {
			panic(err)
		}

		var dState stateless.State
		switch event.Event {
		case libvirt.DOMAIN_EVENT_STARTED:
			dState = state.DesktopStateStarted

		default:
			dState = state.DesktopStateUnknown
		}

		desktop, err := h.desktops.Get(ctx, id)
		if err != nil {
			if !errors.Is(err, pool.ErrValueNotFound) {
				panic(err)
			}

			xml, err := d.GetXMLDesc(libvirt.DomainXMLFlags(0))
			if err != nil {
				panic(err)
			}

			desktop = &pool.Desktop{
				ID:    id,
				Hyper: h.host,
				XML:   xml,
			}
			// if err := h.desktops.Set(context.Background(), desktop); err != nil {
			// 	panic(err)
			// }

			return
		}

		desktop.SetState(dState)

		// TODO: THIS SHOULD BE A TRIGGER AND NOT A STATE!
		if err := h.desktops.Set(context.Background(), desktop); err != nil {
			panic(err)
		}
	})
	if err != nil {
		return nil, fmt.Errorf("register desktop events handler: %w", err)
	}

	h.domEventID = domEventID

	if err := conn.SetKeepAlive(5, 3); err != nil {
		return nil, fmt.Errorf("set libvirt keepalive: %w", err)
	}

	return h, nil
}

// Close closes the libvirt connection with the hypervisor
func (h *Hyper) Close(ctx context.Context) error {
	h.conn.DomainEventDeregister(h.domEventID)

	h.conn.Close()

	hyper, err := h.hypers.Get(ctx, h.host)
	if err != nil {
		return err
	}

	// TODO: There are two messages sent to redis
	if err := h.hypers.Fire(hyper, state.HyperStateDown); err != nil {
		if err := h.hypers.Fire(hyper, state.HyperStateUnknown); err != nil {
			return err
		}
	}

	return nil
}

func (h *Hyper) Ready() error {
	hyper := &pool.Hyper{Host: h.host}
	hyper.SetState(state.HyperStateReady)
	if err := h.hypers.Set(context.Background(), hyper); err != nil {
		return fmt.Errorf("register hypervisor in redis: %w", err)
	}

	return nil
}
