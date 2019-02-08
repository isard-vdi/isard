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

package list

import (
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

// VMList is the complete response of the API
type VMList struct {
	VMs []*VM `json:"vms"`
}

// VM is an individual Virtual Machine
type VM struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

// Call calls the Isard API and returns a list of all the VMs of a specific user
func Call(webRequest mocks.WebRequest, token string) (*VMList, error) {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return &VMList{}, err
	}

	url := config.BaseURL + "/pxe/list?tkn=" + token

	body, code, err := webRequest.Get(url)
	if err != nil {
		return &VMList{}, err

	} else if code != 200 {
		return &VMList{}, fmt.Errorf("HTTP Code: %d", code)
	}

	listVMsResponse := &VMList{}

	err = json.Unmarshal(body, &listVMsResponse)
	if err != nil {
		return &VMList{}, err
	}

	return listVMsResponse, nil
}
