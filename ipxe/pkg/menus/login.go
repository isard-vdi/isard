package menus

import (
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateLogin generates a login iPXE menu
func GenerateLogin() (string, error) {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		menu := `#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`

		return menu, err
	}

	url := config.BaseURL + "/pxe/boot/login"

	menu := fmt.Sprintf(`#!ipxe
set username
set password
login
chain %s?usr=${username:uristring}&pwd=${password:uristring}`, url)

	return menu, nil
}
