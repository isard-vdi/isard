package isardvdi_test

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi-sdk-go"
)

func newClient(t *testing.T) *isardvdi.Client {
	cli, err := isardvdi.NewClient(&isardvdi.Cfg{
		Host:        "https://localhost",
		IgnoreCerts: true,
	})

	if err != nil {
		t.Fatal(err)
	}

	tkn, err := cli.AuthForm(context.Background(), "default", "fry", "fry")
	// tkn, err := cli.AuthForm(context.Background(), "jhony", "jhony", "jhony")
	if err != nil {
		t.Fatal(err)
	}

	cli.SetToken(tkn)

	return cli
}
