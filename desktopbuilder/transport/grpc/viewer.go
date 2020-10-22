package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/desktopbuilder/pkg/proto"

	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	cmnProto "gitlab.com/isard/isardvdi/common/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) ViewerGet(ctx context.Context, req *proto.ViewerGetRequest) (*proto.ViewerGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"xml": &req.Xml,
	}); err != nil {
		return nil, err
	}

	v, err := d.DesktopBuilder.ViewerGet(req.Xml)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get desktop viewer: %v", err)
	}

	rsp := &proto.ViewerGetResponse{
		Viewer: &cmnProto.Viewer{},
	}

	for _, s := range v.Spice {
		rsp.Viewer.Spice = append(rsp.Viewer.Spice, &cmnProto.Viewer_Spice{
			Pwd:     s.Pwd,
			Port:    int32(s.Port),
			TlsPort: int32(s.TLSPort),
		})
	}

	for _, v := range v.VNC {
		rsp.Viewer.Vnc = append(rsp.Viewer.Vnc, &cmnProto.Viewer_Vnc{
			Pwd:           v.Pwd,
			Port:          int32(v.Port),
			WebsocketPort: int32(v.WebsocketPort),
		})
	}

	return rsp, nil
}
