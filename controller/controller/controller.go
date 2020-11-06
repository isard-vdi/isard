package controller

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/common/pkg/pool"
	"gitlab.com/isard/isardvdi/common/pkg/proto"

	desktopBuilderProto "gitlab.com/isard/isardvdi/desktopbuilder/pkg/proto"
	hyperProto "gitlab.com/isard/isardvdi/hyper/pkg/proto"
	orchestratorProto "gitlab.com/isard/isardvdi/orchestrator/pkg/proto"
	"google.golang.org/grpc"
)

type Interface interface {
	DesktopStart(id string) (*proto.Viewer, error)
}

type Controller struct {
	desktops *pool.DesktopPool

	desktopBuilderConn *grpc.ClientConn
	orchestratorConn   *grpc.ClientConn
}

func New() (*Controller, error) {
	// proto.NewControllerClient(cc grpc.ClientConnInterface)
	return nil, nil
}

func (c *Controller) DesktopStart(ctx context.Context, id string) (*proto.Viewer, error) {
	var xml string

	// Check if the desktop is already started
	d, err := c.desktops.Get(id)
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
		orchestratorRsp, err := orchestratorProto.NewOrchestratorClient(c.orchestratorConn).GetHyper(ctx, &orchestratorProto.GetHyperRequest{
			// TODO:
			// desktopBuilderRsp.Persistent
			// desktopBuilderRsp.GPU
		})
		if err != nil {
			return nil, err
		}

		// Prepare the disk(s)

		// Start the desktop
		hyperConn, err := grpc.Dial(fmt.Sprintf("%s:%d", orchestratorRsp.Host, 1312), grpc.WithInsecure())
		if err != nil {
			// TODO: Set hyper to unknown?
			return nil, fmt.Errorf("dial gRPC hypervisor: %w", err)
		}
		hyperRsp, err := hyperProto.NewHyperClient(hyperConn).DesktopStart(ctx, &hyperProto.DesktopStartRequest{
			Xml: desktopBuilderRsp.Xml,
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
