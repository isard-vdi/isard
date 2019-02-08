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

package login

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

type body struct {
	Username string `json:"usr"`
	Password string `json:"pwd"`
}

// Call tries to login using the Isard API and if it succeeds, returns a token
func Call(webRequest mocks.WebRequest, username string, password string) (string, error) {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return "", err
	}

	url := config.BaseURL + "/pxe/login"

	encodedBody, err := json.Marshal(body{
		Username: username,
		Password: password,
	})
	if err != nil {
		return "", err
	}

	body := bytes.NewBuffer(encodedBody)

	rsp, code, err := webRequest.Post(url, body)
	if err != nil {
		return "", err

	} else if code != 200 {
		return "", fmt.Errorf("HTTP Code: %d", code)
	}

	var token struct {
		Token string `json:"tkn"`
	}

	err = json.Unmarshal(rsp, &token)
	if err != nil {
		return "", err
	}

	return token.Token, nil
}
