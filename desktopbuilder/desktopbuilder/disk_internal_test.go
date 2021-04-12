package desktopbuilder

import (
	"sort"
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/pkg/model"
)

func TestDiskOrder(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Disks         []*model.HardwareDisk
		ExpectedDisks []*model.HardwareDisk
	}{
		"should order the disks correctly": {
			Disks: []*model.HardwareDisk{
				{
					Order: 0,
					Disk: &model.Disk{
						Name: "1st in list",
					},
				},
				{
					Order: 3,
					Disk: &model.Disk{
						Name: "2nd in list",
					},
				},
				{
					Order: 2,
					Disk: &model.Disk{
						Name: "3rd in list",
					},
				},
				{
					Order: 0,
					Disk: &model.Disk{
						Name: "4th in list",
					},
				},
			},
			ExpectedDisks: []*model.HardwareDisk{
				{
					Order: 0,
					Disk: &model.Disk{
						Name: "1st in list",
					},
				},
				{
					Order: 0,
					Disk: &model.Disk{
						Name: "4th in list",
					},
				},
				{
					Order: 2,
					Disk: &model.Disk{
						Name: "3rd in list",
					},
				},
				{
					Order: 3,
					Disk: &model.Disk{
						Name: "2nd in list",
					},
				},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			sort.Sort(diskOrder(tc.Disks))

			assert.Equal(tc.ExpectedDisks, tc.Disks)
		})
	}
}

func TestBuildDisk(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Desktop     *model.Desktop
		Disk        *model.HardwareDisk
		Order       int
		ExpectedXML string
	}{
		"should build a qcow2 disk correctly": {
			Desktop: &model.Desktop{
				Entity: &model.Entity{
					UUID: "entityuuid",
				},
				User: &model.User{
					UUID: "useruuid",
				},
			},
			Disk: &model.HardwareDisk{
				Disk: &model.Disk{
					UUID: "diskuuid",
					Type: model.DiskTypeQcow2,
				},
			},
			Order: 3,
			ExpectedXML: `<disk type="file" device="disk">
  <driver name="qemu" type="qcow2"></driver>
  <source file="/opt/isard/disks/entityuuid/useruuid/diskuuid.qcow2"></source>
  <target dev="sdd" bus="virtio"></target>
</disk>`,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			d := &DesktopBuilder{
				storageBasePath: "/opt/isard/disks",
			}
			disk := d.buildDisk(tc.Desktop, tc.Disk, tc.Order)

			xml, err := disk.Marshal()

			assert.NoError(err)
			assert.Equal(tc.ExpectedXML, xml)
		})
	}
}
