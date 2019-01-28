package menus_test

import (
	"fmt"
	"io/ioutil"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

var generateBootTests = []struct {
	arch  string
	token string
	vmID  string
}{
	{
		arch:  "i386",
		token: "JDAUQOO8K4W1g-tNb0_XdB5hArgLMr-XhhGj3ew8JdE",
		vmID:  "_nefix_Alpine_Linux",
	},
}

func TestGenerateBoot(t *testing.T) {
	if err := os.MkdirAll("images/i386", 0755); err != nil {
		t.Fatalf("error preparing the test: error creating the directories: %v", err)
	}

	netboot := []byte(`#!ipxe
kernel {{.BaseURL}}/pxe/boot/vmlinuz?arch=${buildarch:uristring} base_url={{.BaseURL}} tkn={{.Token}} id={{.VMID}} init=/nix/store/x056i5cpbk8fyavvlcbzrr7aw8b97gz4-nixos-system-nixos-19.03pre166366.22b7449aacb/init loglevel=4
initrd {{.BaseURL}}/pxe/boot/initrd?arch=${buildarch:uristring}
boot
`)

	if err := ioutil.WriteFile("images/i386/netboot.ipxe", netboot, 0644); err != nil {
		t.Fatalf("error preparing the test: error creating the file: %v", err)
	}

	for _, tt := range generateBootTests {

		t.Run("should work as expected", func(t *testing.T) {
			expectedRsp := fmt.Sprintf(`#!ipxe
kernel https://isard.domain.com/pxe/boot/vmlinuz?arch=${buildarch:uristring} base_url=https://isard.domain.com tkn=%s id=%s init=/nix/store/x056i5cpbk8fyavvlcbzrr7aw8b97gz4-nixos-system-nixos-19.03pre166366.22b7449aacb/init loglevel=4
initrd https://isard.domain.com/pxe/boot/initrd?arch=${buildarch:uristring}
boot
`, tt.token, tt.vmID)

			menu, err := menus.GenerateBoot(tt.arch, tt.token, tt.vmID)
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}
		})

		t.Run("there's an error reading the configuration", func(t *testing.T) {
			initialFolder, err := os.Getwd()
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			err = os.Chdir("/")
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			expectedRsp := `#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`
			expectedErr := "open config.yml: permission denied"

			menu, err := menus.GenerateBoot(tt.arch, tt.token, tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}

			err = os.Chdir(initialFolder)
			if err != nil {
				t.Fatalf("error finishing the test %v", err)
			}
		})

		t.Run("there's an error reading the boot menu", func(t *testing.T) {
			if err := os.RemoveAll("images"); err != nil {
				t.Fatalf("error finishing the tests: %v", err)
			}

			expectedRsp := `#!ipxe
echo There was an error booting. Your client architecture might not be supported. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`
			expectedErr := "open images/i386/netboot.ipxe: no such file or directory"

			menu, err := menus.GenerateBoot(tt.arch, tt.token, tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}
		})
	}

	// Clean the generated configuration file
	if err := os.Remove("config.yml"); err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
