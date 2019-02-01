/*
 * Copyright (C) 2019 Néfix Estrada <nefixestrada@gmail.com>
 * Author: Néfix Estrada <nefixestrada@gmail.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

package menus

import (
	"io/ioutil"
	"log"
	"text/template"

	"github.com/isard-vdi/isard-ipxe/pkg/api/list"

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
