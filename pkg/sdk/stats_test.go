package isardvdi_test

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestStatsDeploymentByCategory(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	deployments, err := cli.StatsDeploymentByCategory(context.Background())

	assert.NoError(err)

	b, err := json.Marshal(deployments)
	assert.NoError(err)

	fmt.Println(string(b))

	assert.Nil(deployments)
}

func TestStatsUsers(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	users, err := cli.StatsUsers(context.Background())

	b, _ := json.Marshal(users)
	fmt.Println(string(b))

	assert.NoError(err)
	assert.Nil(users)
}

func TestStatsDesktops(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	desktops, err := cli.StatsDesktops(context.Background())

	b, _ := json.Marshal(desktops)
	fmt.Println(string(b))

	assert.NoError(err)
	assert.Nil(desktops)
}

func TestStatsTemplates(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	templates, err := cli.StatsTemplates(context.Background())

	b, _ := json.Marshal(templates)
	fmt.Println(string(b))

	assert.NoError(err)
	assert.Nil(templates)
}

func TestStatsHypervisors(t *testing.T) {
	assert := assert.New(t)

	cli := newClient(t)

	hypervisors, err := cli.StatsHypervisors(context.Background())

	b, _ := json.Marshal(hypervisors)
	fmt.Println(string(b))

	assert.NoError(err)
	assert.Nil(hypervisors)
}
