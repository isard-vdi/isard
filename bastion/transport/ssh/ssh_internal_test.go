package ssh

import (
	"crypto/ed25519"
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"golang.org/x/crypto/ssh"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// testKey builds a deterministic ed25519 SSH key from a seed byte, and returns it both as a
// public key and in its authorized_keys representation.
func testKey(t *testing.T, seed byte) (ssh.PublicKey, string) {
	t.Helper()

	rawSeed := make([]byte, ed25519.SeedSize)
	for i := range rawSeed {
		rawSeed[i] = seed
	}

	key, err := ssh.NewPublicKey(ed25519.NewKeyFromSeed(rawSeed).Public())
	require.NoError(t, err)

	return key, string(ssh.MarshalAuthorizedKey(key))
}

func TestBastionCheckAuthorizedKeys(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	key, authKey := testKey(t, 1)
	_, otherAuthKey := testKey(t, 2)

	cases := map[string]struct {
		PrepareDB   func(*r.Mock)
		Target      *model.Target
		Expected    bool
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {},
			Target: &model.Target{
				ID:        "target-own-key",
				UserID:    "user-own-key",
				DesktopID: "desktop-own-key",
				SSH: model.TargetSSH{
					AuthorizedKeys: []string{otherAuthKey, authKey},
				},
			},
			Expected: true,
		},
		"should skip the target authorized keys that can't be parsed": {
			PrepareDB: func(m *r.Mock) {},
			Target: &model.Target{
				ID:        "target-unparseable-key",
				UserID:    "user-unparseable-key",
				DesktopID: "desktop-unparseable-key",
				SSH: model.TargetSSH{
					AuthorizedKeys: []string{"not an SSH key at all", authKey},
				},
			},
			Expected: true,
		},
		"should authorize the target user bastion ssh key": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-with-key")).Once().Return([]any{
					map[string]any{
						"id":              "user-with-key",
						"bastion_ssh_key": authKey,
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-user-key",
				UserID:    "user-with-key",
				DesktopID: "desktop-user-key",
			},
			Expected: true,
		},
		"should authorize the deployment owner bastion ssh key": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-deployment")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-deployment",
						"tag": "deployment-with-owner",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-with-owner")).Once().Return([]any{
					map[string]any{
						"id":   "deployment-with-owner",
						"user": "deployment-owner",
					},
				}, nil)

				m.On(r.Table("users").Get("deployment-owner")).Once().Return([]any{
					map[string]any{
						"id":              "deployment-owner",
						"bastion_ssh_key": authKey,
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-deployment-owner",
				UserID:    "user-without-key",
				DesktopID: "desktop-of-deployment",
			},
			Expected: true,
		},
		"should authorize a deployment co owner bastion ssh key": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-2")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-2",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-deployment-2")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-deployment-2",
						"tag": "deployment-with-co-owners",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-with-co-owners")).Once().Return([]any{
					map[string]any{
						"id":        "deployment-with-co-owners",
						"user":      "deployment-owner-2",
						"co_owners": []string{"deployment-co-owner"},
					},
				}, nil)

				m.On(r.Table("users").Get("deployment-owner-2")).Once().Return([]any{
					map[string]any{
						"id":              "deployment-owner-2",
						"bastion_ssh_key": otherAuthKey,
					},
				}, nil)

				m.On(r.Table("users").Get("deployment-co-owner")).Once().Return([]any{
					map[string]any{
						"id":              "deployment-co-owner",
						"bastion_ssh_key": authKey,
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-deployment-co-owner",
				UserID:    "user-without-key-2",
				DesktopID: "desktop-of-deployment-2",
			},
			Expected: true,
		},
		"should not authorize if the desktop is not part of a deployment": {
			// The DB stores the tag of a desktop that isn't part of a deployment as false,
			// which decodes to "0". The deployments table must not be queried for it.
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-3")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-3",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-without-deployment")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-without-deployment",
						"tag": false,
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-without-deployment",
				UserID:    "user-without-key-3",
				DesktopID: "desktop-without-deployment",
			},
			Expected: false,
		},
		"should not authorize if the desktop has no tag at all": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-4")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-4",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-without-tag")).Once().Return([]any{
					map[string]any{
						"id": "desktop-without-tag",
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-without-tag",
				UserID:    "user-without-key-4",
				DesktopID: "desktop-without-tag",
			},
			Expected: false,
		},
		"should not authorize if the target user doesn't exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-missing")).Once().Return([]any{}, nil)

				m.On(r.Table("domains").Get("desktop-of-missing-user")).Once().Return([]any{
					map[string]any{
						"id": "desktop-of-missing-user",
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-missing-user",
				UserID:    "user-missing",
				DesktopID: "desktop-of-missing-user",
			},
			Expected: false,
		},
		"should not authorize if the target user bastion ssh key can't be parsed": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-broken-key")).Once().Return([]any{
					map[string]any{
						"id":              "user-broken-key",
						"bastion_ssh_key": "not an SSH key at all",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-broken-key")).Once().Return([]any{
					map[string]any{
						"id": "desktop-of-broken-key",
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-broken-key",
				UserID:    "user-broken-key",
				DesktopID: "desktop-of-broken-key",
			},
			Expected: false,
		},
		"should not authorize if the target has no user": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("domains").Get("desktop-without-user")).Once().Return([]any{
					map[string]any{
						"id": "desktop-without-user",
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-without-user",
				DesktopID: "desktop-without-user",
			},
			Expected: false,
		},
		"should not authorize if the desktop doesn't exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-9")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-9",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-missing")).Once().Return([]any{}, nil)
			},
			Target: &model.Target{
				ID:        "target-missing-desktop",
				UserID:    "user-without-key-9",
				DesktopID: "desktop-missing",
			},
			Expected: false,
		},
		"should not authorize if the deployment doesn't exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-5")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-5",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-missing-deployment")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-missing-deployment",
						"tag": "deployment-missing",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-missing")).Once().Return([]any{}, nil)
			},
			Target: &model.Target{
				ID:        "target-missing-deployment",
				UserID:    "user-without-key-5",
				DesktopID: "desktop-of-missing-deployment",
			},
			Expected: false,
		},
		"should not authorize if no deployment user key matches": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-10")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-10",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-deployment-3")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-deployment-3",
						"tag": "deployment-without-matches",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-without-matches")).Once().Return([]any{
					map[string]any{
						"id":   "deployment-without-matches",
						"user": "deployment-owner-3",
					},
				}, nil)

				m.On(r.Table("users").Get("deployment-owner-3")).Once().Return([]any{
					map[string]any{
						"id":              "deployment-owner-3",
						"bastion_ssh_key": otherAuthKey,
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-deployment-no-match",
				UserID:    "user-without-key-10",
				DesktopID: "desktop-of-deployment-3",
			},
			Expected: false,
		},
		"should not authorize if no key matches": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-other-key")).Once().Return([]any{
					map[string]any{
						"id":              "user-other-key",
						"bastion_ssh_key": otherAuthKey,
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-other-key")).Once().Return([]any{
					map[string]any{
						"id": "desktop-of-other-key",
					},
				}, nil)
			},
			Target: &model.Target{
				ID:        "target-other-key",
				UserID:    "user-other-key",
				DesktopID: "desktop-of-other-key",
				SSH: model.TargetSSH{
					AuthorizedKeys: []string{otherAuthKey},
				},
			},
			Expected: false,
		},
		"should return an error if loading the target user fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-db-error")).Once().Return(nil, errors.New("connection refused"))
			},
			Target: &model.Target{
				ID:        "target-user-db-error",
				UserID:    "user-db-error",
				DesktopID: "desktop-of-user-db-error",
			},
			ExpectedErr: "check the target user SSH key: load user from DB: connection refused",
		},
		"should return an error if loading the desktop fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-6")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-6",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-db-error")).Once().Return(nil, errors.New("connection refused"))
			},
			Target: &model.Target{
				ID:        "target-desktop-db-error",
				UserID:    "user-without-key-6",
				DesktopID: "desktop-db-error",
			},
			ExpectedErr: "check the deployment users SSH keys: load desktop from DB: connection refused",
		},
		"should return an error if loading the deployment fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-7")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-7",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-deployment-db-error")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-deployment-db-error",
						"tag": "deployment-db-error",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-db-error")).Once().Return(nil, errors.New("connection refused"))
			},
			Target: &model.Target{
				ID:        "target-deployment-db-error",
				UserID:    "user-without-key-7",
				DesktopID: "desktop-of-deployment-db-error",
			},
			ExpectedErr: "check the deployment users SSH keys: load deployment from DB: connection refused",
		},
		"should return an error if loading a deployment co owner fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("user-without-key-8")).Once().Return([]any{
					map[string]any{
						"id": "user-without-key-8",
					},
				}, nil)

				m.On(r.Table("domains").Get("desktop-of-co-owner-db-error")).Once().Return([]any{
					map[string]any{
						"id":  "desktop-of-co-owner-db-error",
						"tag": "deployment-co-owner-db-error",
					},
				}, nil)

				m.On(r.Table("deployments").Get("deployment-co-owner-db-error")).Once().Return([]any{
					map[string]any{
						"id":   "deployment-co-owner-db-error",
						"user": "deployment-owner-db-error",
					},
				}, nil)

				m.On(r.Table("users").Get("deployment-owner-db-error")).Once().Return(nil, errors.New("connection refused"))
			},
			Target: &model.Target{
				ID:        "target-co-owner-db-error",
				UserID:    "user-without-key-8",
				DesktopID: "desktop-of-co-owner-db-error",
			},
			ExpectedErr: `check the deployment users SSH keys: check the deployment user "deployment-owner-db-error" SSH key: load user from DB: connection refused`,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			b := &bastion{
				log: log.New("test", "debug"),
				db:  mock,
			}

			ok, err := b.checkAuthorizedKeys(t.Context(), tc.Target, key)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.Expected, ok)

			mock.AssertExpectations(t)
		})
	}
}
