package hyper_test

import (
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestList(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest      func(h *hyper.Hyper)
		ExpectedErr      string
		ExpectedDesktops []string
	}{
		"should list the desktops correctly": {
			ExpectedDesktops: []string{"test"},
		},
		"should return an error if there's an error listing the desktops": {
			PrepareTest: func(h *hyper.Hyper) {
				h.Close()
			},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_INVALID_CONN,
				Domain:  libvirt.ErrorDomain(20),
				Message: "invalid connection pointer in virConnectListAllDomains",
			}.Error(),
			ExpectedDesktops: []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			h, err := hyper.New(hyper.TestLibvirtDriver(t))
			require.NoError(err)

			defer h.Close()

			if tc.PrepareTest != nil {
				tc.PrepareTest(h)
			}

			desktops, err := h.List()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			names := []string{}
			for _, desktop := range desktops {
				name, err := desktop.GetName()
				assert.NoError(err)

				names = append(names, name)
			}

			assert.Equal(tc.ExpectedDesktops, names)
		})
	}
}
