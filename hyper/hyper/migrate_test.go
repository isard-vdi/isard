package hyper_test

// import (
// 	"testing"

// 	"gitlab.com/isard/isardvdi/hyper/hyper"

// 	"github.com/stretchr/testify/assert"
// 	"github.com/stretchr/testify/require"
// 	"libvirt.org/libvirt-go"
// )

// func TestMigrate(t *testing.T) {
// 	require := require.New(t)
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		PrepareDesktop func(h *hyper.Hyper) *libvirt.Domain
// 		ExpectedErr    string
// 	}{
// 		// TODO: The test driver doesn't support P2P live migration. Try this with qemu drivers
// 		// "migrate the desktop correctly": {
// 		// 	PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
// 		// 		desktop, err := h.Start(hyper.TestMinDesktopXML(t), &hyper.StartOptions{})
// 		// 		require.NoError(err)

// 		// 		return desktop
// 		// 	},
// 		// },
// 	}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			const target = "test:///default"

// 			h1, err := hyper.New(hyper.TestLibvirtDriver(t))
// 			require.NoError(err)

// 			h2, err := hyper.New(target)
// 			require.NoError(err)

// 			var name string
// 			desktop := tc.PrepareDesktop(h1)
// 			if desktop != nil {
// 				defer desktop.Free()

// 				name, err = desktop.GetName()
// 				require.NoError(err)
// 			}

// 			err = h1.Migrate(desktop, target)

// 			if tc.ExpectedErr != "" {
// 				assert.EqualError(err, tc.ExpectedErr)
// 			} else {
// 				assert.NoError(err)
// 			}

// 			migratedDesktop, err := h2.Get(name)
// 			assert.NoError(err)
// 			defer migratedDesktop.Free()

// 			migratedName, err := migratedDesktop.GetName()
// 			assert.NoError(err)

// 			assert.Equal(name, migratedName)

// 			state, _, err := migratedDesktop.GetState()
// 			assert.NoError(err)

// 			assert.Equal(libvirt.DOMAIN_RUNNING, state)
// 		})
// 	}
// }
