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

package cert

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// IsValid states if the server has already trusted CA or not. If it does, there's no need of the cert
var IsValid = false

// Check updates the IsValid variable
func Check() error {
	IsValid = true

	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		IsValid = false

		return fmt.Errorf("error checking the certificate: %v", err)
	}

	_, err = http.Get(config.BaseURL)
	if err != nil {
		IsValid = false

		// Check that the error is because a self signed certificate
		if strings.Split(err.Error(), ": ")[1] != "x509" {
			return fmt.Errorf("error checking the certificate: %v", err)
		}
	}

	return nil
}
