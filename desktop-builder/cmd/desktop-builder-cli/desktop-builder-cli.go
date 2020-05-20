package main

import (
	"context"
	"fmt"

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
	rsp, err := cli.XMLGet(context.Background(), &proto.XMLGetRequest{Id: "test", Template: "win10"})
	if err != nil {
		panic(err)
	}

	fmt.Println(rsp.Xml)

	// _, err = cli.GetXml(context.Background(), &proto.GetXmlRequest{
	// 	Type: proto.GetXmlRequest_DESKTOP_TYPE_KVM,
	// 	Name: "test",
	// 	Os: &proto.GetXmlRequest_DesktopOS{
	// 		Type: &proto.GetXmlRequest_DesktopOS_DesktopOSType{
	// 			Arch:    proto.GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_ARCH_X86_64,
	// 			Machine: proto.GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_MACHINE_Q35,
	// 			Type:    proto.GetXmlRequest_DesktopOS_DesktopOSType_DESKTOP_OS_TYPE_TYPE_HVM,
	// 		},
	// 	},
	// 	Devices: &proto.GetXmlRequest_DesktopDevices{
	// 		Input: []*proto.GetXmlRequest_DesktopDevices_DesktopDeviceInput{
	// 			{
	// 				Type: proto.GetXmlRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_TYPE_KEYBOARD,
	// 				Bus:  proto.GetXmlRequest_DesktopDevices_DesktopDeviceInput_DESKTOP_DEVICE_INPUT_BUS_PS2,
	// 			},
	// 		},
	// 		Graphic: []*proto.GetXmlRequest_DesktopDevices_DesktopDeviceGraphic{
	// 			{Type: proto.GetXmlRequest_DesktopDevices_DesktopDeviceGraphic_DESKTOP_DEVICE_GRAPHIC_TYPE_SPICE,
	// 				Listen: "0.0.0.0",
	// 			},
	// 		},
	// 		Video: []*proto.GetXmlRequest_DesktopDevices_DesktopDeviceVideo{
	// 			{
	// 				Model: &proto.GetXmlRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel{
	// 					Type: proto.GetXmlRequest_DesktopDevices_DesktopDeviceVideo_DesktopDeviceVideoModel_DESKTOP_DEVICE_VIDEO_MODEL_TYPE_QXL,
	// 				},
	// 			},
	// 		},
	// 	},
	// 	Memory: &proto.GetXmlRequest_DesktopMemory{
	// 		Value: 2,
	// 		Unit:  "G",
	// 	},
	// 	Vcpu: &proto.GetXmlRequest_DesktopVCPU{
	// 		Num:       2,
	// 		Placement: "static",
	// 	},
	// })
	if err != nil {
		panic(err)
	}
}
