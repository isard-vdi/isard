package menus_test

import (
	"fmt"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

var generateBootTests = []struct {
	token string
	vmID  string
}{
	{
		token: "JDAUQOO8K4W1g-tNb0_XdB5hArgLMr-XhhGj3ew8JdE",
		vmID:  "_nefix_Alpine_Linux",
	},
}

func TestGenerateBoot(t *testing.T) {
	for _, tt := range generateBootTests {

		t.Run("should work as expected", func(t *testing.T) {
			expectedRsp := fmt.Sprintf(`#!ipxe
kernel https://isard.domain.com/pxe/vmlinuz tkn=%s id=%s initrd=https://isard.domain.com/pxe/initrd
initrd https://isard.domain.com/pxe/initrd
boot`, tt.token, tt.vmID)

			menu, err := menus.GenerateBoot(tt.token, tt.vmID)
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

			menu, err := menus.GenerateBoot(tt.token, tt.vmID)
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
	}

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
