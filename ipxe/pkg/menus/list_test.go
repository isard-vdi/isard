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

package menus_test

import (
	"errors"
	"io"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/menus"
)

type testWebRequest struct{}

func (testWebRequest) Get(url string) ([]byte, int, error) {
	return endpoints[url].Body, endpoints[url].Code, endpoints[url].Err
}

func (testWebRequest) Post(url string, body io.Reader) ([]byte, int, error) {
	return nil, 500, nil
}

var endpoints map[string]endpointKey

type endpointKey struct {
	Body []byte
	Code int
	Err  error
}

var generateListTests = []struct {
	token     string
	username  string
	endpoints map[string]endpointKey
	menu      string
}{
	{
		token:    "DCJmySp6ydeq4tuTCJhQZ3xnH28q-mitGQN9YKnv22A",
		username: "nefix",
		endpoints: map[string]endpointKey{
			"https://isard.domain.com/pxe/list?tkn=DCJmySp6ydeq4tuTCJhQZ3xnH28q-mitGQN9YKnv22A": {
				Body: []byte(`{
					"vms": [
						{
							"id": "_nefix_KDE_Neon_5",
							"name": "KDE Neon 5",
							"description": "This is a VM that's using KDE Neon 5"
						},
						{
							"id": "_nefix_Debian_9",
							"name": "Debian 9",
							"description": "This is a VM that's using Debian 9"
						},
						{
							"id": "_nefix_Arch_Linux",
							"name": "Arch Linux",
							"description": "This is a VM that's using Arch Linux"
						}
					]
				}`),
				Code: 200,
				Err:  nil,
			},
			"https://isard.domain.com/pxe/list?tkn=individualVM": {
				Body: []byte(`{
					"vms": [
						{
							"id": "_nefix_Debian_9",
							"name": "Debian 9",
							"description": "This is a VM that's using Debian 9"
						}
					]
				}`),
				Code: 200,
				Err:  nil,
			},
			"https://isard.domain.com/pxe/list?tkn=invalidtoken": {
				Body: []byte(`{}`),
				Code: 403,
				Err:  nil,
			},
			"https://isard.domain.com/pxe/list?tkn=error": {
				Body: []byte(`{}`),
				Code: 500,
				Err:  errors.New("testing error"),
			},
		},
		menu: `#!ipxe
set tkn DCJmySp6ydeq4tuTCJhQZ3xnH28q-mitGQN9YKnv22A
menu IsardVDI - nefix
item _nefix_KDE_Neon_5 KDE Neon 5 -->
item _nefix_Debian_9 Debian 9 -->
item _nefix_Arch_Linux Arch Linux -->
item
item --gap -- ---- Actions ----
item bootFromDisk Boot from disk -->
item reboot Reboot -->
item poweroff Poweroff -->
choose target && goto ${target}
:_nefix_KDE_Neon_5
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_KDE_Neon_5&arch=${buildarch:uristring}
:_nefix_Debian_9
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_Debian_9&arch=${buildarch:uristring}
:_nefix_Arch_Linux
chain https://isard.domain.com/pxe/boot/start?tkn=${tkn:uristring}&id=_nefix_Arch_Linux&arch=${buildarch:uristring}
:bootFromDisk
sanboot --no-describe --drive 0x80
:reboot
reboot
:poweroff
poweroff
`,
	},
}

func TestGenerateList(t *testing.T) {
	for _, tt := range generateListTests {
		endpoints = tt.endpoints

		t.Run("should work as expected", func(t *testing.T) {
			expectedRsp := tt.menu

			menu, err := menus.GenerateList(testWebRequest{}, tt.token, tt.username)
			if err != nil {
				t.Errorf("unexpected error %v", err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %v, but got %v", expectedRsp, menu)
			}
		})

		t.Run("should return a chain menu if the user has only one VM", func(t *testing.T) {
			expectedRsp := `#!ipxe
chain https://isard.domain.com/pxe/boot/start?tkn=individualVM&id=_nefix_Debian_9`

			menu, err := menus.GenerateList(testWebRequest{}, "individualVM", tt.username)
			if err != nil {
				t.Errorf("unexpected error %v", err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}
		})

		t.Run("should chain to the login menu if there's a 403 error", func(t *testing.T) {
			expectedRsp := `#!ipxe
set username
set password
login
chain https://isard.domain.com/pxe/boot/auth?usr=${username:uristring}&pwd=${password:uristring}`
			expectedErr := "HTTP Code: 403"

			menu, err := menus.GenerateList(testWebRequest{}, "invalidtoken", tt.username)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %v, but got %v", expectedRsp, menu)
			}
		})

		t.Run("should return an error menu if there's an error reading the configuration", func(t *testing.T) {
			initialFolder, err := os.Getwd()
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			err = os.Chdir("/")
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			expectedRsp := `#!ipxe
echo There was an error reading the configuration file. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`
			expectedErr := "open config.yml: permission denied"
			menu, err := menus.GenerateList(testWebRequest{}, tt.token, tt.username)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}

			err = os.Chdir(initialFolder)
			if err != nil {
				t.Fatalf("error finishing the test %v", err)
			}
		})

		t.Run("should return an error menu if there's an error calling the API", func(t *testing.T) {
			expectedRsp := `#!ipxe
echo There was an error calling the API. If this error persists, contact your IsardVDI administrator.
prompt Press any key to try again
reboot`
			expectedErr := "testing error"

			menu, err := menus.GenerateList(testWebRequest{}, "error", tt.username)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if menu != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, menu)
			}
		})
	}

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
