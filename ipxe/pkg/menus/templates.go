package menus

import (
	"io/ioutil"
	"log"
	"text/template"

	"github.com/isard-vdi/isard-ipxe/pkg/client/list"

	rice "github.com/GeertJohan/go.rice"
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

func parseBootTemplate(arch string) (*template.Template, error) {
	b, err := ioutil.ReadFile("images/" + arch + "/netboot.ipxe")
	if err != nil {
		return nil, err
	}

	tmpl, err := template.New("boot-" + arch).Parse(string(b))
	if err != nil {
		return nil, err
	}

	return tmpl, nil
}
