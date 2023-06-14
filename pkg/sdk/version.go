package isardvdi

import (
	"runtime/debug"
)

var Version = "Unknown version"

func init() {
	if bi, ok := debug.ReadBuildInfo(); ok {
		for _, d := range bi.Deps {
			if d.Path == "gitlab.com/isard/isardvdi-sdk-go" {
				Version = d.Version
			}
		}
	}
}
