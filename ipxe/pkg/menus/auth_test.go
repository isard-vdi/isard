package menus_test

import (
	"fmt"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

var generateAuthTests = []struct {
	token    string
	username string
}{
	{
		token:    "LnSnIl3E30Q71OZbRIyxbm7Bqp50-KbYtxZEArkDhrA",
		username: "nefix",
	},
}

func TestGenerateAuth(t *testing.T) {
	for _, tt := range generateAuthTests {
		t.Run("should work as expected", func(t *testing.T) {
			expectedRsp := fmt.Sprintf(`#!ipxe
chain https://isard.domain.com/pxe/boot/list?tkn=%s&usr=%s`, tt.token, tt.username)

			menu, err := menus.GenerateAuth(tt.token, tt.username)
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

			menu, err := menus.GenerateAuth(tt.token, tt.username)
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
