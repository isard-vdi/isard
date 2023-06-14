package isardvdi_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi-sdk-go"
)

func TestUserOwnsDesktop(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	err := cli.UserOwnsDesktop(context.Background(), &isardvdi.UserOwnsDesktopOpts{
		ProxyHyperHost: "isaaaard-hypervisor",
		Port:           5900,
	})
	assert.ErrorIs(err, isardvdi.ErrForbidden)
}
