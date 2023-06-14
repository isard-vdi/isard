package isardvdi_test

import (
	"context"
	"testing"
)

// func TestAdminUserCreate(t *testing.T) {
// 	assert := assert.New(t)

// 	cli := newClient(t)

// 	unix := strconv.Itoa(int(time.Now().Unix()))
// 	name := fmt.Sprintf("testing-%s", unix)

// 	u, err := cli.AdminUserCreate(
// 		context.Background(),
// 		"local",
// 		"user",
// 		"default",
// 		"default-default",
// 		unix,
// 		name,
// 		"IsardVDI",
// 		strings.ToTitle(name),
// 	)

// 	if err != nil {
// 		assert.NoError(err)
// 	}

// 	assert.Equal(&client.User{}, u)
// }

func TestAdminHypervisorOnlyForced(t *testing.T) {
	cli := newClient(t)

	if err := cli.AdminHypervisorOnlyForced(context.Background(), "isard-hypervisor", false); err != nil {
		t.Fatal(err)
	}
}
