package hyper_test

import (
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestStart(t *testing.T) {
	defer hyper.TestDesktopsCleanup(t)

	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		XML           string
		Opts          *hyper.StartOptions
		RealConn      bool
		ExpectedErr   string
		ExpectedState libvirt.DomainState
	}{
		"should start the desktop correctly": {
			XML:           hyper.TestMinDesktopXML(t),
			Opts:          &hyper.StartOptions{},
			ExpectedState: libvirt.DOMAIN_RUNNING,
		},
		"should start the desktop paused correcly": {
			XML:           hyper.TestMinDesktopXML(t, "kvm"),
			Opts:          &hyper.StartOptions{Paused: true},
			RealConn:      true,
			ExpectedState: libvirt.DOMAIN_PAUSED,
		},
		"should return an error if there's an error starting the desktop": {
			XML:  "<domain",
			Opts: &hyper.StartOptions{},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_XML_DETAIL,
				Domain:  libvirt.ErrorDomain(20),
				Message: "(domain_definition):1: Couldn't find end of Start Tag domain line 1\n<domain\n-------^",
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

			desktop, err := h.Start(tc.XML, tc.Opts)
			if desktop != nil {
				defer desktop.Free()
			}

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
