// Package desktopbuilder does everything XML-related with the desktops and libvirt;
// from generating the desktopb boot XML to extracting the Viewer from the desktop booted XML
package desktopbuilder

import (
	"context"

	"github.com/go-pg/pg/v10"
)

// Interface has all the methods that the desktopbuilder package should publish. It's used to mock the package
type Interface interface {
	// XMLGet generates a XML for a desktop
	XMLGet(ctx context.Context, id string) (string, error)
	// ViewerGet returns a Viewer form the booted desktop XML
	ViewerGet(xml string) (*Viewer, error)
}

// DesktopBuilder implements Interface
type DesktopBuilder struct {
	db              *pg.DB
	storageBasePath string
}

// New creates a DesktopBuilder struct, using the provided database and storage base path
func New(db *pg.DB, storageBasePath string) *DesktopBuilder {
	return &DesktopBuilder{db, storageBasePath}
}
