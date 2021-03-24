package hyper_test

// import (
// 	"testing"

// 	"gitlab.com/isard/isardvdi/hyper/hyper"

// 	"github.com/stretchr/testify/assert"
// 	"libvirt.org/libvirt-go"
// )

// func TestHyperNew(t *testing.T) {
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		URI         string
// 		ExpectedErr string
// 	}{
// 		"should create the hypervisor correctly": {},
// 		"should return an error if there's an error connecting to the libvirt daemon": {
// 			URI: ":::://///",
// 			ExpectedErr: "connect to libvirt: " + libvirt.Error{
// 				Code:    libvirt.ERR_INTERNAL_ERROR,
// 				Domain:  libvirt.ErrorDomain(45),
// 				Message: "internal error: Unable to parse URI :::://///",
// 			}.Error(),
// 		},
// 	}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			h, err := hyper.New(tc.URI)
// 			if h != nil {
// 				defer h.Close()
// 			}

// 			if tc.ExpectedErr != "" {
// 				assert.EqualError(err, tc.ExpectedErr)
// 			} else {
// 				assert.NoError(err)
// 			}
// 		})
// 	}
// }
