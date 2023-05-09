package collector

import (
	"encoding/xml"
	"testing"

	"github.com/stretchr/testify/assert"
	"libvirt.org/go/libvirtxml"
)

func TestParseIsardMetadata(t *testing.T) {
	assert := assert.New(t)

	metadata, err := parseIsardMetadata(&libvirtxml.DomainMetadata{XML: `<libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
      <libosinfo:os id="http://debian.org/debian/10"/>
    </libosinfo:libosinfo>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:who user_id="local-default-admin-admin" group_id="default-default" category_id="default"/>
      <isard:parent parent_id="_local-default-admin-admin-elsax"/>
    </isard:isard>`})

	expectedMetadata := &IsardMetadata{
		XMLName: xml.Name{
			Local: "isard",
			Space: "http://isardvdi.com",
		},
		Who: &IsardMetadataWho{
			XMLName: xml.Name{
				Local: "who",
				Space: "http://isardvdi.com",
			},
			UserID:     "local-default-admin-admin",
			GroupID:    "default-default",
			CategoryID: "default",
		},
	}

	assert.NoError(err)
	assert.Equal(expectedMetadata, metadata)
}
