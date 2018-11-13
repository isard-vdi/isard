package menus

import (
	"bytes"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateAuth returns the menu that needs to be generated after a correct call at the AuthHandler
func GenerateAuth(token string, username string) (string, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		buf := new(bytes.Buffer)

		t := parseTemplate("error.ipxe")
		t.Execute(buf, menuTemplateData{
			Err: "reading the configuration file",
		})

		return buf.String(), err
	}

	buf := new(bytes.Buffer)

	t := parseTemplate("auth.ipxe")
	t.Execute(buf, menuTemplateData{
		BaseURL:  config.BaseURL,
		Token:    token,
		Username: username,
	})

	return buf.String(), nil
}
