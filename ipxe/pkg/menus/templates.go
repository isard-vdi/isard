package menus

import (
	"log"
	"text/template"

	"github.com/GeertJohan/go.rice"

	"github.com/isard-vdi/isard-ipxe/pkg/client/list"
)

type menuTemplateData struct {
	BaseURL  string
	Token    string
	Username string
	Err      string
	VMs      []*list.VM
	VMID     string
}

func parseTemplate(tmplName string) *template.Template {
	templateBox, err := rice.FindBox("assets")
	if err != nil {
		log.Fatal(err)
	}

	tmplString, err := templateBox.String(tmplName)
	if err != nil {
		log.Fatal(err)
	}

	tmpl, err := template.New(tmplName).Parse(tmplString)
	if err != nil {
		log.Fatal(err)
	}

	return tmpl
}
