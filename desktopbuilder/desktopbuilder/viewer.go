package desktopbuilder

import (
	"errors"
	"fmt"

	libvirtxml "libvirt.org/libvirt-go-xml"
)

var (
	// ErrNoGraphics gets returned when a Viewer is requested but the desktop has no graphics
	ErrNoGraphics = errors.New("the desktop has no graphics")
)

// Viewer has info from all the graphic types of a desktop
type Viewer struct {
	Spice []*ViewerSpice
	VNC   []*ViewerVNC
}

// ViewerSpice has all the info to connect to a desktop using the SPICE protocol
type ViewerSpice struct {
	Pwd        string
	Port       int
	TLSPort    int
	PwdValidTo string
}

// ViewerVNC has all the info to connect to a desktop using the VNC protocol
type ViewerVNC struct {
	Pwd           string
	Port          int
	WebsocketPort int
	PwdValidTo    string
}

// ViewerGet returns all the viewers from a desktop XML
func (d *DesktopBuilder) ViewerGet(xml string) (*Viewer, error) {
	desktop := &libvirtxml.Domain{}
	if err := desktop.Unmarshal(xml); err != nil {
		return nil, fmt.Errorf("unmarshal desktop XML: %w", err)
	}

	if len(desktop.Devices.Graphics) <= 0 {
		return nil, ErrNoGraphics
	}

	v := &Viewer{}
	for _, g := range desktop.Devices.Graphics {
		if g.Spice != nil {
			v.Spice = append(v.Spice, &ViewerSpice{
				Pwd:        g.Spice.Passwd,
				Port:       g.Spice.Port,
				TLSPort:    g.Spice.TLSPort,
				PwdValidTo: g.Spice.PasswdValidTo,
			})
		}

		if g.VNC != nil {
			v.VNC = append(v.VNC, &ViewerVNC{
				Pwd:           g.VNC.Passwd,
				Port:          g.VNC.Port,
				WebsocketPort: g.VNC.WebSocket,
				PwdValidTo:    g.VNC.PasswdValidTo,
			})
		}
	}

	return v, nil
}
