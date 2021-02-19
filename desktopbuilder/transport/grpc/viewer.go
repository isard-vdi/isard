package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/common"
	"gitlab.com/isard/isardvdi/pkg/proto/desktopbuilder"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) ViewerGet(ctx context.Context, req *desktopbuilder.ViewerGetRequest) (*desktopbuilder.ViewerGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"xml": &req.Xml,
	}); err != nil {
		return nil, err
	}

	v, err := d.DesktopBuilder.ViewerGet(req.Xml)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get desktop viewer: %v", err)
	}

	rsp := &desktopbuilder.ViewerGetResponse{
		Viewer: &common.Viewer{},
	}

	for _, s := range v.Spice {
		rsp.Viewer.Spice = append(rsp.Viewer.Spice, &common.Viewer_Spice{
			Pwd:     s.Pwd,
			Port:    int32(s.Port),
			TlsPort: int32(s.TLSPort),
		})
	}

	for _, v := range v.VNC {
		rsp.Viewer.Vnc = append(rsp.Viewer.Vnc, &common.Viewer_Vnc{
			Pwd:           v.Pwd,
			Port:          int32(v.Port),
			WebsocketPort: int32(v.WebsocketPort),
		})
	}

	return rsp, nil
}
