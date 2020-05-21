package grpc

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/hyper/pkg/proto"
)

func (h *HyperServer) DesktopStart(ctx context.Context, req *proto.DesktopStartRequest) (*proto.DesktopStartResponse, error) {
	xml, err := h.env.Hyper.DesktopStart(ctx, req.Xml, req.Password)
	//panic(fmt.Sprintf(dom.Marshal()))
	if err != nil {
		return &proto.DesktopStartResponse{Xml: ""}, fmt.Errorf("desktop not started")
	}
	return &proto.DesktopStartResponse{Xml: xml}, nil
}

func (h *HyperServer) DesktopStop(ctx context.Context, req *proto.DesktopStopRequest) (*proto.DesktopStopResponse, error) {
	result, err := h.env.Hyper.DesktopStop(ctx, req.Id)
	//panic(fmt.Sprintf(dom.Marshal()))
	if err != nil {
		return &proto.DesktopStopResponse{Result: result}, fmt.Errorf("desktop not started")
	}
	return &proto.DesktopStopResponse{Result: result}, nil
}

func (h *HyperServer) DesktopList(ctx context.Context, req *proto.DesktopListRequest) (*proto.DesktopListResponse, error) {
	domains, err := h.env.Hyper.DesktopList(ctx)
	//panic(fmt.Sprintf(dom.Marshal()))
	if err != nil {
		return &proto.DesktopListResponse{Id: domains}, fmt.Errorf("desktop not started")
	}
	return &proto.DesktopListResponse{Id: domains}, nil
}

func (h *HyperServer) DesktopXMLGet(ctx context.Context, req *proto.DesktopXMLGetRequest) (*proto.DesktopXMLGetResponse, error) {
	xml, err := h.env.Hyper.DesktopXMLGet(ctx, req.Id)
	//panic(fmt.Sprintf(dom.Marshal()))
	if err != nil {
		return &proto.DesktopXMLGetResponse{Xml: xml}, fmt.Errorf("desktop not started")
	}
	return &proto.DesktopXMLGetResponse{Xml: xml}, nil
}
