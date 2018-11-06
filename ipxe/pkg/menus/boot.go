package menus

import (
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateBoot generates the menu that boots the client image
func GenerateBoot(token string, vmID string) (string, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		menu := `#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`

		return menu, err
	}

	menu := fmt.Sprintf(`#!ipxe
kernel %s/pxe/vmlinuz tkn=%s id=%s initrd=%s/pxe/initrd
initrd %s/pxe/initrd
boot`, config.BaseURL, token, vmID, config.BaseURL, config.BaseURL)

	return menu, nil
}
