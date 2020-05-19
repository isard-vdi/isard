package grpc

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"
	libvirtxml "libvirt.org/libvirt-go-xml"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DesktopBuilderServer) GetXml(ctx context.Context, req *proto.GetXmlRequest) (*proto.GetXmlResponse, error) {
	inputs := []libvirtxml.DomainInput{}
	for _, i := range req.Devices.Input {
		inputs = append(inputs, libvirtxml.DomainInput{
			Type: proto.GetXmlRequestDesktopDeviceInputTypeString(i.Type),
			Bus:  proto.GetXmlRequestDesktopDeviceInputBusString(i.Bus),
		})
	}

	graphics := []libvirtxml.DomainGraphic{}
	for _, g := range req.Devices.Graphic {
		if g.Spice {
			graphics = append(graphics, libvirtxml.DomainGraphic{
				Spice: &libvirtxml.DomainGraphicSpice{
					Listen: "0.0.0.0",
				},
			})
		}
	}

	videos := []libvirtxml.DomainVideo{}
	for _, v := range req.Devices.Video {
		videos = append(videos, libvirtxml.DomainVideo{
			Model: libvirtxml.DomainVideoModel{
				Type: proto.GetXmlRequestDesktopDeviceVideoModelTypeString(v.Model.Type),
			},
		})
	}

	dom := &libvirtxml.Domain{
		Type: proto.GetXmlRequestDesktopTypeString(req.Type),
		Name: req.Name,
		OS: &libvirtxml.DomainOS{
			Type: &libvirtxml.DomainOSType{
				Arch:    proto.GetXmlRequestDesktopOSTypeArchString(req.Os.Type.Arch),
				Machine: proto.GetXmlRequestDesktopOSTypeMachineString(req.Os.Type.Machine),
				Type:    proto.GetXmlRequestDesktopOSTypeTypeString(req.Os.Type.Type),
			},
		},
		Devices: &libvirtxml.DomainDeviceList{
			Inputs:   inputs,
			Graphics: graphics,
			Videos:   videos,
		},
		Memory: &libvirtxml.DomainMemory{
			Value: uint(req.Memory.Value),
			Unit:  req.Memory.Unit,
		},
		VCPU: &libvirtxml.DomainVCPU{
			Value:     int(req.Vcpu.Num),
			Placement: req.Vcpu.Placement,
		},
	}

	panic(fmt.Sprintf(dom.Marshal()))

	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}
