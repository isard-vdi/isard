package sdk

import (
	"runtime/debug"
)

var Version = "Unknown version"

func init() {
	if bi, ok := debug.ReadBuildInfo(); ok {
		for _, d := range bi.Deps {
			if d.Path == "gitlab.com/isard/isardvdi/pkg/sdk" {
				Version = d.Version
			}
		}
	}
}
