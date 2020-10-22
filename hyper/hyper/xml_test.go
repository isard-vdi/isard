package hyper_test

import (
	"errors"
	"io/ioutil"
	"testing"

	"gitlab.com/isard/isardvdi/hyper/hyper"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"libvirt.org/libvirt-go"
)

func TestXMLGet(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	okCaseXML, err := ioutil.ReadFile("testdata/xml_test-should_return_the_XML_correctly.xml")
	require.NoError(err)

	cases := map[string]struct {
		PrepareDesktop func(h *hyper.Hyper) *libvirt.Domain
		ExpectedXML    string
		ExpectedErr    string
	}{
		"should return the XML correctly": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				desktop, err := h.Get("test")
				require.NoError(err)

				return desktop
			},
			ExpectedXML: string(okCaseXML),
		},
		"should return an error if there's an error getting the XML": {
			PrepareDesktop: func(h *hyper.Hyper) *libvirt.Domain {
				return &libvirt.Domain{}
			},
			ExpectedErr: libvirt.Error{
				Code:    libvirt.ERR_INVALID_DOMAIN,
				Domain:  libvirt.ErrorDomain(6),
				Message: "invalid domain pointer in virDomainGetXMLDesc",
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

			xml, err := h.XMLGet(desktop)

			if tc.ExpectedErr == "" {
				assert.NoError(err)
				assert.Equal(tc.ExpectedXML, xml)
			} else {
				var e libvirt.Error
				if errors.As(err, &e) {
					assert.Equal(tc.ExpectedErr, e.Error())
				} else {
					assert.EqualError(err, tc.ExpectedErr)
				}
			}

		})
	}
}
