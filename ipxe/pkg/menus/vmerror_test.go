package menus_test

import (
	"errors"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

func TestGenerateVMError(t *testing.T) {
	t.Run("should work as expected", func(t *testing.T) {
		expectedRsp := `#!ipxe
set username nefix
set password p4$$w0rd!
echo The VM start has failed: testing error
prompt Press any key to go back
chain https://isard.domain.com/pxe/boot/login?usr=${username:uristring}&pwd=${password:uristring}`

		menu, err := menus.GenerateVMError(errors.New("testing error"), "nefix", "p4$$w0rd!")
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

		menu, err := menus.GenerateLogin()
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

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
