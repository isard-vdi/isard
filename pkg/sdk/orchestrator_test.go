package isardvdi_test

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestOrchestratorHypervisorList(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	hypervisors, err := cli.OrchestratorHypervisorList(context.Background())

	assert.NoError(err)

	b, err := json.Marshal(hypervisors)
	assert.NoError(err)

	fmt.Println(string(b))

	assert.Nil(hypervisors)
}

func TestOrchestratorHypervisorGet(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	hypervisor, err := cli.OrchestratorHypervisorGet(context.Background(), "isard-hyiipervisor")

	assert.NoError(err)

	b, err := json.Marshal(hypervisor)
	assert.NoError(err)

	fmt.Println(hypervisor)

	fmt.Println(string(b))

	assert.Nil(hypervisor)
}

func TestOrchestratorHypervisorManage(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	err := cli.OrchestratorHypervisorManage(context.Background(), "isard-hypervisor")

	assert.NoError(err)
	assert.False(true)
}

func TestOrchestratorHypervisorUnmanage(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	err := cli.OrchestratorHypervisorUnmanage(context.Background(), "isard-hypervisor")

	assert.NoError(err)
	assert.False(true)
}

func TestOrchestratorHypervisorAddToDeadRow(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	deadRow, err := cli.OrchestratorHypervisorAddToDeadRow(context.Background(), "isard-hypervisor")

	assert.NoError(err)

	fmt.Printf("%s\n", deadRow)

	assert.Nil(deadRow)
}

func TestOrchestratorHypervisorRemoveFromDeadRow(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	err := cli.OrchestratorHypervisorRemoveFromDeadRow(context.Background(), "isard-hypervisor")

	assert.NoError(err)
	assert.False(true)
}

func TestOrchestratorHypervisorStopDesktops(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	err := cli.OrchestratorHypervisorStopDesktops(context.Background(), "isard-hypervisor")

	assert.NoError(err)

	assert.False(true)
}
