// +build ignore

package main

import (
	"bytes"
	"fmt"
	"os/exec"

	"gitlab.com/isard/isardvdi/pkg/state"

	"github.com/qmuntal/stateless"
)

func main() {
	hyper := stateless.NewStateMachine(state.HyperStateReady)
	state.NewHyperState(hyper)

	desktop := stateless.NewStateMachine(state.DesktopStatePreCreating)
	state.NewDesktopState(desktop)

	stateMachines := map[string]*stateless.StateMachine{
		"hyper":   hyper,
		"desktop": desktop,
	}

	for name, m := range stateMachines {
		cmd := exec.Command("dot", "-T", "svg", "-o", name+".svg")
		cmd.Stdin = bytes.NewReader([]byte(m.ToGraph()))

		if out, err := cmd.CombinedOutput(); err != nil {
			fmt.Printf("error generating the %s states diagram: %v: %s", name, err, out)
		}
	}
}
