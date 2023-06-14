package isardvdi_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestDesktopCreate(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)
	d, err := cli.DesktopCreate(context.Background(), "EEESLAX TESTING", "_local-default-admin-admin-elsax")

	assert.NoError(err)
	assert.Nil(d)
}
