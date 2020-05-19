package main

import (
	"context"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"
	"google.golang.org/grpc"
)

func main() {
	conn, err := grpc.Dial(":1312", grpc.WithInsecure())
	if err != nil {
		panic(err)
	}
	defer conn.Close()

	cli := proto.NewDesktopBuilderClient(conn)

	_, err = cli.GetXml(context.Background(), &proto.DesktopStartRequest{
		Type: proto.DesktopStartRequest_DESKTOP_TYPE_KVM,
		Name: "test",
		Os: &proto.DesktopStartRequest_DesktopOS{
			Type: &proto.DesktopStartRequest_DesktopOS_DesktopOSType{
				Arch: proto.DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_ARCH_X86_64,
				Machine: proto.DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_MACHINE_PC_i44FX_4_2,
				Type: proto.DesktopStartRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_TYPE_HVM,
			},
		},
		Devices: &proto.DesktopStartRequest_DesktopDevices{
			Input: []*proto.DesktopStartRequest_DesktopDevices_DesktopDeviceInput{
				{
					Type: proto.DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_TYPE_KEYBOARD,
					Bus: proto.DesktopStartRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_BUS_PS2,
				},
			},
			Graphic: []*proto.DesktopStartRequest_DesktopDevices_DesktopDeviceGraphic{
				{
					Spice: true,
				},
			},
			Video: []*proto.DesktopStartRequest_DesktopDevices_DesktopDeviceVideo{
				{
					Model: &proto.DesktopStartRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel{
						Type: proto.DesktopStartRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DESKTOP_DEVICE_VIDEO_MODEL_TYPE_QXL,
					},
				},
			},
		},
		Memory: &proto.DesktopStartRequest_DesktopMemory{
			Value: 2,
			Unit: "G",
		},
		Vcpu: &proto.DesktopStartRequest_DesktopVCPU{
			Num: 2,
			Placement: "static",
		},
	})
	if err != nil {
		panic(err)
	}
}