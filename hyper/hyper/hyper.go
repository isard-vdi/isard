package hyper

import (
	"fmt"

	"github.com/isard-vdi/isard/hyper/env"

	"libvirt.org/libvirt-go"
)

type Interface interface {
	Start(xml string, paused bool) (string, error)
	Stop(id string) error
	XMLGet(id string) (string, error)
	List() ([]libvirt.Domain, error)
	Close() error
}

type Hyper struct {
	env  *env.Env
	conn *libvirt.Connect
}

func New(env *env.Env, uri string) (*Hyper, error) {
	if uri == "" {
		uri = "qemu:///system"
	}

	conn, err := libvirt.NewConnect(uri)
	if err != nil {
		return nil, fmt.Errorf("connect to libvirt: %w", err)
	}

	return &Hyper{env, conn}, nil
}

func (h *Hyper) Close() error {
	_, err := h.conn.Close()
	return err
}
