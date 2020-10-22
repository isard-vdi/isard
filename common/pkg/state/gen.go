// +build ignore

package main

import (
	"bytes"
	"fmt"
	"os/exec"

	"gitlab.com/isard/isardvdi/common/pkg/state"
)

func main() {
	m := state.NewHyperState()

	cmd := exec.Command("dot", "-T", "svg", "-o", "hyper.svg")
	cmd.Stdin = bytes.NewReader([]byte(m.ToGraph()))

	if out, err := cmd.CombinedOutput(); err != nil {
		fmt.Printf("error generating the hyper states diagram: %v: %s", err, out)
	}
}
