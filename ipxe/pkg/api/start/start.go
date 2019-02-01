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

package start

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

type body struct {
	Token string `json:"tkn"`
	ID    string `json:"id"`
}

// Call calls the Isard API and starts a VM
func Call(webRequest mocks.WebRequest, token string, vmID string) error {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return err
	}

	url := config.BaseURL + "/pxe/start"

	encodedBody, err := json.Marshal(body{
		Token: token,
		ID:    vmID,
	})
	if err != nil {
		return err
	}

	body := bytes.NewBuffer(encodedBody)

	rspBody, code, err := webRequest.Post(url, body)
	if err != nil {
		return err
	}

	if code != 200 {
		if code == 500 {
			type err500 struct {
				Code    int    `json:"code"`
				Message string `json:"msg"`
			}

			rspErr := &err500{}

			err = json.Unmarshal(rspBody, rspErr)
			if err != nil {
				return err
			}

			if rspErr.Code == 2 {
				return fmt.Errorf("VM start failed: %s", rspErr.Message)
			}
		}

		return fmt.Errorf("HTTP Code: %d", code)
	}

	return nil
}
