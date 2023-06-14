package isardvdi_test

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi-sdk-go"
)

func TestMaintenace(t *testing.T) {
	cli, err := isardvdi.NewClient(&isardvdi.Cfg{Host: "http://localhost"})
	if err != nil {
		t.Fatal(err)
	}

	t.Fatal(cli.Maintenance(context.Background()))
}
