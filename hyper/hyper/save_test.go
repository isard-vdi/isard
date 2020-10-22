package hyper_test

import (
	"io/ioutil"
	"os"
	"path/filepath"
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestSave(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDesktop func(h *hyper.Hyper) *libvirt.Domain
		ExpectedErr    string
		FinalAsserts   func(h *hyper.Hyper, desktop_name string, path string)
	}{
		"should save the desktop correctly": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				desktop, err := h.Start(hyper.TestMinDesktopXML(t), &hyper.StartOptions{})
				require.NoError(err)

				return desktop
			},
			FinalAsserts: func(h *hyper.Hyper, name string, path string) {
				err := h.Restore(path)
				assert.NoError(err)

				desktop, _ := h.Get(name)
				state, _, err := desktop.GetState()
				assert.NoError(err)

				assert.Equal(libvirt.DOMAIN_RUNNING, state)
			},
		},
		"should return an error if there's an error saving the desktop": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				return &libvirt.Domain{}
			},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_INVALID_DOMAIN,
				Domain:  libvirt.ErrorDomain(6),
				Message: "invalid domain pointer in virDomainSave",
			}.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			h, err := hyper.New(hyper.TestLibvirtDriver(t))
			require.NoError(err)

			defer h.Close()

			desktop := tc.PrepareDesktop(h)
			if desktop != nil {
				defer desktop.Free()
			}

			tmp, err := ioutil.TempDir("", "isard-test-save")
			require.NoError(err)

			defer os.RemoveAll(tmp)

			path := filepath.Join(tmp, "desktop.img")

			err = h.Save(desktop, path)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)

				name, err := desktop.GetName()
				assert.NoError(err)

				tc.FinalAsserts(h, name, path)
			}
		})
	}
}
