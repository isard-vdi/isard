package diskoperations

import (
	"github.com/isard-vdi/isard/disk-operations/env"
)

type Interface interface {
	// Create(name string, size int64, format DiskFormat, clusterSize DiskClusterSize, prealloc DiskPreallocation, lazyRefcounts bool) error
	Delete(name string) error
	Derivate(name, backingFile string, clusterSize int) error
	// Upload(ctx context.Context, src io.Reader, dst string) error
	// Download(ctx context.Context, url, dst string) error
}

type DiskOperations struct {
	env *env.Env
}

func New(env *env.Env) *DiskOperations {
	return &DiskOperations{env}
}
