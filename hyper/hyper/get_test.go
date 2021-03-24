package hyper_test

// import (
// 	"testing"

// 	"gitlab.com/isard/isardvdi/hyper/hyper"

// 	"github.com/stretchr/testify/assert"
// 	"github.com/stretchr/testify/require"
// 	"libvirt.org/libvirt-go"
// )

// func TestGet(t *testing.T) {
// 	require := require.New(t)
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		Name          string
// 		ExpectedErr   string
// 		ExpectedState libvirt.DomainState
// 	}{
// 		"should get the desktop correctly": {
// 			Name:          "test",
// 			ExpectedState: libvirt.DOMAIN_RUNNING,
// 		},
// 		"should return an error if there's an error getting the desktop": {
// 			ExpectedErr: libvirt.Error{
// 				Code:    libvirt.ERR_NO_DOMAIN,
// 				Domain:  libvirt.ErrorDomain(12),
// 				Message: "Domain not found",
// 			}.Error(),
// 		},
// 	}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			h, err := hyper.New(hyper.TestLibvirtDriver(t))
// 			require.NoError(err)

// 			defer h.Close()

// 			desktop, err := h.Get(tc.Name)
// 			if desktop != nil {
// 				defer desktop.Free()

// 				state, _, err := desktop.GetState()
// 				assert.NoError(err)
// 				assert.Equal(tc.ExpectedState, state)

// 			} else {
// 				assert.Equal(libvirt.DomainState(0), tc.ExpectedState)
// 			}

// 			if tc.ExpectedErr != "" {
// 				assert.EqualError(err, tc.ExpectedErr)
// 			} else {
// 				assert.NoError(err)
// 			}
// 		})
// 	}
// }
