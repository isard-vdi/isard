package menus

import (
	"bytes"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateVMError generates an iPXE menu with an error
func GenerateVMError(vmErr error) (string, error) {
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
	t := parseTemplate("errorVM.ipxe")

	err = t.Execute(buf, menuTemplateData{
		BaseURL: config.BaseURL,
		Err:     fmt.Sprintf("%v", vmErr),
	})

	return buf.String(), err
}
