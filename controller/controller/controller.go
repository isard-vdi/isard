package controller

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/common/pkg/pool"
	"gitlab.com/isard/isardvdi/common/pkg/proto"

	desktopBuilderProto "gitlab.com/isard/isardvdi/desktopbuilder/pkg/proto"
	hyperProto "gitlab.com/isard/isardvdi/hyper/pkg/proto"
	"google.golang.org/grpc"
)

type Interface interface {
	DesktopStart(id string) (*proto.Viewer, error)
}

type Controller struct {
	desktopPool *pool.DesktopPool

	hyperConn          *grpc.ClientConn
	desktopBuilderConn *grpc.ClientConn
}

func New() (*Controller, error) {
	// proto.NewControllerClient(cc grpc.ClientConnInterface)
	return nil, nil
}

func (c *Controller) DesktopStart(ctx context.Context, id string) (*proto.Viewer, error) {
	var xml string

	// Check if the desktop is already started
	d, err := c.desktopPool.Get(id)
	if err != nil {
		if !errors.Is(err, pool.ErrValueNotFound) {
			panic(err)
		}

		// Get the XML for the desktop
		desktopBuilderRsp, err := desktopBuilderProto.NewDesktopBuilderClient(c.desktopBuilderConn).XMLGet(ctx, &desktopBuilderProto.XMLGetRequest{
			Id: id,
		})
		if err != nil {
			return nil, err
		}

		// Ask for the hypervisor

		// Prepare the disk

		// Start the desktop
		hyperRsp, err := hyperProto.NewHyperClient(c.hyperConn).DesktopStart(ctx, &hyperProto.DesktopStartRequest{
			Xml: "XML",
		})
		if err != nil {
			return nil, err
		}
		xml = hyperRsp.Xml

	} else {
		xml = d.XML
	}

	// Get the Viewer XML
	viewer, err := desktopBuilderProto.NewDesktopBuilderClient(c.desktopBuilderConn).ViewerGet(ctx, &desktopBuilderProto.ViewerGetRequest{
		Xml: xml,
	})
	if err != nil {
		return nil, err
	}

	return viewer.Viewer, nil
}
