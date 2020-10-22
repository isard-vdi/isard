package hyper_test

import (
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestRestore(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest   func(h *hyper.Hyper, path string) string
		ExpectedErr   string
		ExpectedState libvirt.DomainState
	}{
		"should restore the desktop correctly": {
			PrepareTest: func(h *hyper.Hyper, path string) string {
				desktop, err := h.Start(hyper.TestMinDesktopXML(t), &hyper.StartOptions{})
				require.NoError(err)

				name, err := desktop.GetName()
				require.NoError(err)

				err = h.Save(desktop, path)
				require.NoError(err)

				return name
			},
			ExpectedState: libvirt.DOMAIN_RUNNING,
		},
		"should return an error as the file is invalid": {
			PrepareTest: func(h *hyper.Hyper, path string) string {
				err := ioutil.WriteFile(path, []byte("invalid file content"), 0755)
				require.NoError(err)

				return ""
			},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_INTERNAL_ERROR,
				Domain:  libvirt.ErrorDomain(12),
				Message: "internal error: mismatched header magic",
			}.Error(),
		},
		"should return an error if the path is incorrect or file missing": {
			PrepareTest: func(h *hyper.Hyper, path string) string {
				return ""
			},
			ExpectedErr: "stat %s: no such file or directory",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			h, err := hyper.New(hyper.TestLibvirtDriver(t))
			require.NoError(err)

			defer h.Close()

			tmp, err := ioutil.TempDir("", "isard-test-restore")
			require.NoError(err)

			defer os.RemoveAll(tmp)

			path := filepath.Join(tmp, "desktop.img")
			desktopName := tc.PrepareTest(h, path)

			err = h.Restore(path)

			if tc.ExpectedErr != "" {
				if strings.Contains(tc.ExpectedErr, "%") {
					tc.ExpectedErr = fmt.Sprintf(tc.ExpectedErr, path)
				}

				assert.EqualError(err, tc.ExpectedErr)

			} else {
				assert.NoError(err)
			}

			if tc.ExpectedState != libvirt.DomainState(0) {
				desktop, err := h.Get(desktopName)
				assert.NoError(err)

				state, _, err := desktop.GetState()
				assert.NoError(err)

				assert.Equal(tc.ExpectedState, state)
			}
		})
	}
}
