package collector

import (
	"encoding/xml"
	"testing"

	"github.com/stretchr/testify/assert"
	"libvirt.org/go/libvirt"
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
		Parent: &IsardMetadataParent{
			XMLName: xml.Name{
				Local: "parent",
				Space: "http://isardvdi.com",
			},
			ParentID: "_local-default-admin-admin-elsax",
		},
	}

	assert.NoError(err)
	assert.Equal(expectedMetadata, metadata)
}

func TestSplitDomainsIntoBatches(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		RunningDomains  []*libvirt.Domain
		ExpectedBatches [][]*libvirt.Domain
	}{
		"should batch correctly with a number smaller than the batch size": {
			RunningDomains: make([]*libvirt.Domain, 3),
			ExpectedBatches: [][]*libvirt.Domain{
				make([]*libvirt.Domain, 3),
			},
		},
		"should batch correctly with a small batch": {
			RunningDomains: make([]*libvirt.Domain, 53),
			ExpectedBatches: [][]*libvirt.Domain{
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 3),
			},
		},
		"should batch correctly with a big batch": {
			RunningDomains: make([]*libvirt.Domain, 420),
			ExpectedBatches: [][]*libvirt.Domain{
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 50),
				make([]*libvirt.Domain, 20),
			},
		},
		"should return a 0 batch number if there are no domains": {
			RunningDomains:  make([]*libvirt.Domain, 0),
			ExpectedBatches: [][]*libvirt.Domain{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			batches := splitDomainsIntoBatches(tc.RunningDomains)

			assert.Equal(tc.ExpectedBatches, batches)
		})
	}
}

func TestInterfaceMAC(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Interfaces  []libvirtxml.DomainInterface
		Dev         string
		ExpectedMAC string
	}{
		"should return the MAC of the matching target": {
			Interfaces: []libvirtxml.DomainInterface{
				{Target: &libvirtxml.DomainInterfaceTarget{Dev: "vnet0"}, MAC: &libvirtxml.DomainInterfaceMAC{Address: "52:54:00:00:00:01"}},
				{Target: &libvirtxml.DomainInterfaceTarget{Dev: "vnet1"}, MAC: &libvirtxml.DomainInterfaceMAC{Address: "52:54:00:00:00:02"}},
			},
			Dev:         "vnet1",
			ExpectedMAC: "52:54:00:00:00:02",
		},
		"should skip an interface without a target": {
			Interfaces: []libvirtxml.DomainInterface{
				{MAC: &libvirtxml.DomainInterfaceMAC{Address: "52:54:00:00:00:01"}},
				{Target: &libvirtxml.DomainInterfaceTarget{Dev: "vnet1"}, MAC: &libvirtxml.DomainInterfaceMAC{Address: "52:54:00:00:00:02"}},
			},
			Dev:         "vnet1",
			ExpectedMAC: "52:54:00:00:00:02",
		},
		"should return an empty MAC when the matching interface has none": {
			Interfaces: []libvirtxml.DomainInterface{
				{Target: &libvirtxml.DomainInterfaceTarget{Dev: "vnet0"}},
			},
			Dev:         "vnet0",
			ExpectedMAC: "",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			assert.Equal(tc.ExpectedMAC, interfaceMAC(tc.Interfaces, tc.Dev))
		})
	}
}
