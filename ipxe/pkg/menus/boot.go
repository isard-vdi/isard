package menus

import (
	"bytes"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateBoot generates the menu that boots the client image
func GenerateBoot(arch, token, vmID string) (string, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		buf := new(bytes.Buffer)

		t := parseTemplate("error.ipxe")
		if tmplErr := t.Execute(buf, menuTemplateData{
			Err: "reading the configuration file",
		}); tmplErr != nil {
			return buf.String(), tmplErr
		}

		return buf.String(), err
	}

	buf := new(bytes.Buffer)

	t, err := parseBootTemplate(arch)
	if err != nil {
		buf := new(bytes.Buffer)

		t := parseTemplate("error.ipxe")
		if tmplErr := t.Execute(buf, menuTemplateData{
			Err: "booting. Your client architecture might not be supported",
		}); tmplErr != nil {
			return buf.String(), tmplErr
		}

		return buf.String(), err
	}
	err = t.Execute(buf, menuTemplateData{
		BaseURL: config.BaseURL,
		Token:   token,
		VMID:    vmID,
	})

	return buf.String(), err
}
