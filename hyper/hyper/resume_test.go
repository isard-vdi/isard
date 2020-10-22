package hyper_test

import (
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestResume(t *testing.T) {
	defer hyper.TestDesktopsCleanup(t)

	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDesktop func(h *hyper.Hyper) *libvirt.Domain
		RealConn       bool
		ExpectedErr    string
		ExpectedState  libvirt.DomainState
	}{
		"should resume the desktop correctly": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				desktop, err := h.Start(hyper.TestMinDesktopXML(t, "kvm"), &hyper.StartOptions{Paused: true})
				require.NoError(err)

				err = h.Suspend(desktop)
				require.NoError(err)

				return desktop
			},
			RealConn:      true,
			ExpectedState: libvirt.DOMAIN_RUNNING,
		},
		"should return an error if there's an error resuming the desktop": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				return &libvirt.Domain{}
			},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_INVALID_DOMAIN,
				Domain:  libvirt.ErrorDomain(6),
				Message: "invalid domain pointer in virDomainResume",
			}.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			var conn string
			if !tc.RealConn {
				conn = hyper.TestLibvirtDriver(t)
			}

			h, err := hyper.New(conn)
			require.NoError(err)

			defer h.Close()

			desktop := tc.PrepareDesktop(h)
			if desktop != nil {
				defer desktop.Free()
			}

			err = h.Resume(desktop)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.ExpectedState != libvirt.DomainState(0) {
				state, _, err := desktop.GetState()
				assert.NoError(err)

				assert.Equal(tc.ExpectedState, state)
			}
		})
	}
}
