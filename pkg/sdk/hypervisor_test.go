package isardvdi_test

import (
	"context"
	"encoding/json"
	"testing"
)

func TestHypervisorGet(t *testing.T) {
	cli := newClient(t)
	hyper, err := cli.HypervisorGet(context.Background(), "isard-hypervisor")
	if err != nil {
		t.Fatal(err)
	}

	b, err := json.MarshalIndent(hyper, "", "    ")
	if err != nil {
		t.Fatal(err)
	}
	t.Fatal(string(b))
}
