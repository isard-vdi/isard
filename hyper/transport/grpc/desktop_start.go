package grpc

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/hyper/pkg/proto"
	libvirtxml "libvirt.org/libvirt-go-xml"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *HyperServer) DesktopStart(ctx context.Context, req *proto.DesktopStartRequest) (*proto.DesktopStartResponse, error) {
	inputs := []libvirtxml.DomainInput{}
	for _, i := range req.Devices.Input {
		inputs = append(inputs, libvirtxml.DomainInput{
			Type: proto.DesktopStartRequestDesktopDeviceInputTypeString(i.Type),
			Bus:  proto.DesktopStartRequestDesktopDeviceInputBusString(i.Bus),
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
				Type: proto.DesktopStartRequestDesktopDeviceVideoModelTypeString(v.Model.Type),
			},
		})
	}

	dom := &libvirtxml.Domain{
		Type: proto.DesktopStartRequestDesktopTypeString(req.Type),
		Name: req.Name,
		OS: &libvirtxml.DomainOS{
			Type: &libvirtxml.DomainOSType{
				Arch: proto.DesktopStartRequestDesktopOSTypeArchString(req.Os.Type.Arch),  
				Machine: proto.DesktopStartRequestDesktopOSTypeMachineString(req.Os.Type.Machine),
				Type:    proto.DesktopStartRequestDesktopOSTypeTypeString(req.Os.Type.Type),
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
