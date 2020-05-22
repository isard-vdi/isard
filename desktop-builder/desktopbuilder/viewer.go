package desktopbuilder

import (
	"context"
	"fmt"

	libvirtxml "github.com/libvirt/libvirt-go-xml"
)

type Spice struct {
	Passwd  string
	Port    int
	TLSPort int
}

type Vnc struct {
	Passwd    string
	Port      int
	WebSocket int
}

type Viewer struct {
	spice []Spice
	vnc   []Vnc
}

func (db *DesktopBuilder) ViewerGet(ctx context.Context, xml string) (*Viewer, error) {
	desktopcfg := &libvirtxml.Domain{}
	err := desktopcfg.Unmarshal(xml)
	if err != nil {
		return nil, fmt.Errorf("list desktops: %s", err)
	}
	v := &Viewer{}
	for _, g := range desktopcfg.Devices.Graphics {
		//defer g.Free()

		if g.Spice != nil {
			graphic := Spice{
				Passwd:  g.Spice.Passwd,
				Port:    g.Spice.Port,
				TLSPort: g.Spice.TLSPort}
			v.spice = append(v.spice, graphic)
		}

		if g.VNC != nil {
			graphic := Vnc{
				Passwd:    g.VNC.Passwd,
				Port:      g.VNC.Port,
				WebSocket: g.VNC.WebSocket}
			v.vnc = append(v.vnc, graphic)
		}
	}

	return v, nil
}
