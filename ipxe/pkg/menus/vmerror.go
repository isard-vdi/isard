package menus

import (
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateVMError generates an iPXE menu with an error
func GenerateVMError(vmErr error, username string, password string) (string, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		menu := `#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`

		return menu, err
	}

	return fmt.Sprintf(`#!ipxe
set username %s
set password %s
echo The VM start has failed: %v
prompt Press any key to go back
chain %v/pxe/boot/login?usr=${username:uristring}&pwd=${password:uristring}`, username, password, vmErr, config.BaseURL), nil
}
