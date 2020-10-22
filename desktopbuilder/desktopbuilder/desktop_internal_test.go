package desktopbuilder

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/common/pkg/model"
	libvirtxml "libvirt.org/libvirt-go-xml"
)

func TestBuildOSBIOS(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		BIOS *model.DesktopTypeBIOS

		ExpectedXML string
	}{
		"should work as expected": {
			BIOS: &model.DesktopTypeBIOS{
				FirmwareType: model.DesktopFirmwareTypeEFI,
				OSType:       model.DesktopOSTypeXEN,
				Arch:         "x86_64",
				Machine:      "q35",
				Boot: []model.DesktopBootType{
					model.DesktopBootTypeHD,
				},
			},
			ExpectedXML: `<domain>
  <os firmware="efi">
    <type arch="x86_64" machine="q35">xen</type>
    <boot dev="hd"></boot>
  </os>
</domain>`,
		},
		"should generate sensible defaults": {
			ExpectedXML: `<domain>
  <os>
    <type machine="q35">hvm</type>
  </os>
</domain>`,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			os := &libvirtxml.DomainOS{}

			buildOSBIOS(tc.BIOS, os)

			dom := &libvirtxml.Domain{OS: os}
			xml, err := dom.Marshal()
			require.NoError(err)

			assert.Equal(tc.ExpectedXML, xml)
		})
	}
}
