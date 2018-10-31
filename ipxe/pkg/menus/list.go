package menus

import (
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/client/list"
	"github.com/isard-vdi/isard-ipxe/pkg/client/mocks"
	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateList generates an iPXE menu with the VM list
func GenerateList(webRequest mocks.WebRequest, token string, username string) (string, error) {
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
set tkn %s
menu IsardVDI - %s
`, token, username)

	vms, err := list.Call(webRequest, token)
	if err != nil {
		if err.Error() == "HTTP Code: 403" {
			menu = fmt.Sprintf(`#!ipxe
set username
set password
login
chain %v/pxe/boot/login?usr=${username:uristring}&pwd=${password:uristring}`, config.BaseURL)

			return menu, nil
		}

		menu = fmt.Sprintf(`#!ipxe
echo There was an error calling the API. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`)

		return menu, err
	}

	var entries string

	for _, vm := range vms.VMs {
		menu += fmt.Sprintf(`item %s %s -->
`, vm.ID, vm.Name)

		entries += fmt.Sprintf(`:%s
chain %s/pxe/boot/start?tkn=${tkn}&id=%s
`, vm.ID, config.BaseURL, vm.ID)
	}

	menu += `item
item --gap -- ---- Actions ----
item bootFromDisk Boot from disk -->
item reboot Reboot -->
item poweroff Poweroff -->
choose target && goto ${target}
`
	entries += `:bootFromDisk
sanboot --no-describe --drive 0x80
:reboot
reboot
:poweroff
poweroff`

	menu += entries

	return menu, nil
}
