package desktopbuilder

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"
	libvirtxml "github.com/libvirt/libvirt-go-xml"
)

func (d *DesktopBuilder) ViewerGet(ctx context.Context, xml string) (string, error) {
	domcfg := &libvirtxml.Domain{}
	err = domcfg.Unmarshal(xml)
	
	viewer := proto.DesktopBuilderServer.ViewerGet()
	graphics := domcfg.Devices.Graphics
	for _, g := range graphics {
		g.Spice.Passwd
		g.Spice.Port
		g.Spice.TLSPort
		g.VNC.Passwd
		g.VNC.Port
		g.VNC.WebSocket
	}
	
		return "", fmt.Errorf("template not found")
	}
}
