package menus

import (
	"bytes"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateLogin generates a login iPXE menu
func GenerateLogin() (string, error) {
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

	t := parseTemplate("login.ipxe")
	err = t.Execute(buf, menuTemplateData{
		BaseURL: config.BaseURL,
	})

	return buf.String(), err
}
