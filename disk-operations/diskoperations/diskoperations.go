package diskoperations

import "github.com/isard-vdi/isard/disk-operations/env"

type DiskOperations struct {
	env *env.Env
}

func New(env *env.Env) *DiskOperations {
	return &DiskOperations{env}
}
