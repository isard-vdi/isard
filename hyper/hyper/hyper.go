package hyper

import (
	"fmt"

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
	Close() error
}

// Hyper is the implementation of the hyper Interface
type Hyper struct {
	conn *libvirt.Connect
}

// New creates a new Hyper and connects to the libvirt daemon
func New(uri string) (*Hyper, error) {
	if uri == "" {
		uri = "qemu:///system"
	}

	conn, err := libvirt.NewConnect(uri)
	if err != nil {
		return nil, fmt.Errorf("connect to libvirt: %w", err)
	}

	return &Hyper{conn}, nil
}

// Close closes the libvirt connection with the hypervisor
func (h *Hyper) Close() error {
	_, err := h.conn.Close()
	return err
}
