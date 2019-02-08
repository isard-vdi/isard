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
