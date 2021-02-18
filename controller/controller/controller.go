package controller

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/controller/cfg"
	"gitlab.com/isard/isardvdi/pkg/pool"
	"gitlab.com/isard/isardvdi/pkg/proto/common"
	desktopBuilderProto "gitlab.com/isard/isardvdi/pkg/proto/desktopbuilder"
	hyperProto "gitlab.com/isard/isardvdi/pkg/proto/hyper"
	orchestratorProto "gitlab.com/isard/isardvdi/pkg/proto/orchestrator"

	"google.golang.org/grpc"
	_ "google.golang.org/grpc/xds" // Add support for xDS
)

type Interface interface {
	DesktopStart(ctx context.Context, id string) (*common.Viewer, error)
}

type Controller struct {
	desktops *pool.DesktopPool

	desktopBuilderConn *grpc.ClientConn
	desktopBuilder     desktopBuilderProto.DesktopBuilderClient
	orchestratorConn   *grpc.ClientConn
	orchestrator       orchestratorProto.OrchestratorClient
}

func New(cfg cfg.Cfg) (*Controller, error) {
	var err error
	c := &Controller{}

	c.desktopBuilderConn, err = grpc.Dial(cfg.ClientsAddr.DesktopBuilder, grpc.WithInsecure())
	if err != nil {
		return nil, fmt.Errorf("dial desktop builder: %w", err)
	}
	c.desktopBuilder = desktopBuilderProto.NewDesktopBuilderClient(c.desktopBuilderConn)

	c.orchestratorConn, err = grpc.Dial(cfg.ClientsAddr.Orchestrator, grpc.WithInsecure())
	if err != nil {
		return nil, fmt.Errorf("dial orchestrator: %w", err)
	}
	c.orchestrator = orchestratorProto.NewOrchestratorClient(c.desktopBuilderConn)

	return c, nil
}

func (c *Controller) Close() error {
	c.desktopBuilderConn.Close()
	return c.orchestratorConn.Close()
}

func (c *Controller) DesktopStart(ctx context.Context, id string) (*common.Viewer, error) {
	var xml string

	// Check if the desktop is already started
	// TODO: What if the desktop is in an invalid state?
	d, err := c.desktops.Get(id)
	if err != nil {
		if !errors.Is(err, pool.ErrValueNotFound) {
			panic(err)
		}

		// Get the XML for the desktop
		desktopBuilderRsp, err := c.desktopBuilder.XMLGet(ctx, &desktopBuilderProto.XMLGetRequest{
			Id: id,
		})
		if err != nil {
			return nil, err
		}

		// Ask for the hypervisor
		orchestratorRsp, err := c.orchestrator.GetHyper(ctx, &orchestratorProto.GetHyperRequest{
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
	viewer, err := c.desktopBuilder.ViewerGet(ctx, &desktopBuilderProto.ViewerGetRequest{
		Xml: xml,
	})
	if err != nil {
		return nil, err
	}

	return viewer.Viewer, nil
}
