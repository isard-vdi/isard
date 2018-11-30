package menus

import (
	"bytes"

	"github.com/isard-vdi/isard-ipxe/pkg/client/list"
	"github.com/isard-vdi/isard-ipxe/pkg/client/mocks"
	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// GenerateList generates an iPXE menu with the VM list
func GenerateList(webRequest mocks.WebRequest, token string, username string) (string, error) {
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

	vms, err := list.Call(webRequest, token)
	if err != nil {
		if err.Error() == "HTTP Code: 403" {
			buf := new(bytes.Buffer)

			t := parseTemplate("login.ipxe")
			if tmplErr := t.Execute(buf, menuTemplateData{
				BaseURL: config.BaseURL,
			}); tmplErr != nil {
				return buf.String(), tmplErr
			}

			return buf.String(), err
		}

		buf := new(bytes.Buffer)

		t := parseTemplate("error.ipxe")
		if tmplErr := t.Execute(buf, menuTemplateData{
			Err: "calling the API",
		}); tmplErr != nil {
			return buf.String(), tmplErr
		}

		return buf.String(), err
	}

	buf := new(bytes.Buffer)

	if len(vms.VMs) == 1 {
		t := parseTemplate("individualVM.ipxe")
		err = t.Execute(buf, menuTemplateData{
			BaseURL: config.BaseURL,
			Token:   token,
			VMID:    vms.VMs[0].ID,
		})

		return buf.String(), err
	}

	t := parseTemplate("VMList.ipxe")
	err = t.Execute(buf, menuTemplateData{
		BaseURL:  config.BaseURL,
		Token:    token,
		Username: username,
		VMs:      vms.VMs,
	})

	return buf.String(), err
}
