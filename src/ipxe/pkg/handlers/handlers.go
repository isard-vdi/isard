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

package handlers

import (
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/isard-vdi/isard-ipxe/pkg/api/login"
	"github.com/isard-vdi/isard-ipxe/pkg/api/request"
	"github.com/isard-vdi/isard-ipxe/pkg/api/start"
	"github.com/isard-vdi/isard-ipxe/pkg/menus"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

// WebRequest is the struct that is going to use to call the API
var WebRequest mocks.WebRequest = request.Request{}

// LoginHandler is the handler that returns the login menu
func LoginHandler(w http.ResponseWriter, r *http.Request) {
	menu, err := menus.GenerateLogin()
	if err != nil {
		log.Printf("error generating the login menu: %v", err)
	}

	if _, err = fmt.Fprint(w, menu); err != nil {
		log.Printf("error writting the login menu: %v", err)
	}
}

// AuthHandler is the handler that authenticates the user. If the authentication succeeds, it calls the VMListHandler and if it fails,
// it calls the LoginHandler
func AuthHandler(w http.ResponseWriter, r *http.Request) {
	username := r.FormValue("usr")
	password := r.FormValue("pwd")

	token, err := login.Call(WebRequest, username, password)
	if err != nil {
		if err.Error() == "HTTP Code: 401" {
			LoginHandler(w, r)
			return
		}

		log.Printf("error calling the login API endpoint: %v", err)

		var menu string
		menu, err = menus.GenerateError("calling the login API endpoint")
		if err != nil {
			log.Printf("error generating the error menu: %v", err)
		}

		if _, err = fmt.Fprint(w, menu); err != nil {
			log.Printf("error writting the error menu: %v", err)
		}
		return
	}

	menu, err := menus.GenerateAuth(token, username)
	if err != nil {
		log.Printf("error generating the VM error menu: %v", err)
	}

	if _, err = fmt.Fprint(w, menu); err != nil {
		log.Printf("error writting the auth menu: %v", err)
	}
}

// VMListHandler is the handler that returns a list with all the VMs
func VMListHandler(w http.ResponseWriter, r *http.Request) {
	token := r.FormValue("tkn")
	username := r.FormValue("usr")

	menu, err := menus.GenerateList(WebRequest, token, username)
	if err != nil {
		if err.Error() == "HTTP Code: 403" {
			w.WriteHeader(http.StatusForbidden)

		} else {
			log.Printf("error generating the VM list menu: %v", err)
		}
	}

	if _, err = fmt.Fprint(w, menu); err != nil {
		log.Printf("error writting the list menu: %v", err)
	}
}

// StartHandler is the handler that starts the selected VM
func StartHandler(w http.ResponseWriter, r *http.Request) {
	arch := r.FormValue("arch")
	token := r.FormValue("tkn")
	vmID := r.FormValue("id")

	err := start.Call(WebRequest, token, vmID)
	if err != nil {
		if err.Error() == "HTTP Code: 403" {
			LoginHandler(w, r)
			return
		}

		if strings.HasPrefix(err.Error(), "VM start failed: ") {
			var menu string
			menu, err = menus.GenerateVMError(errors.New(strings.Split(err.Error(), ": ")[1]))
			if err != nil {
				log.Printf("error generating the VM error menu: %v", err)
			}

			if _, err = fmt.Fprint(w, menu); err != nil {
				log.Printf("error writting the error menu: %v", err)
			}
			return
		}

		log.Printf("error calling the start API endpoint: %v", err)

		var menu string
		menu, err = menus.GenerateError("calling the start API endpoint")
		if err != nil {
			log.Printf("error generating the error menu: %v", err)
		}

		if _, err = fmt.Fprint(w, menu); err != nil {
			log.Printf("error writting the error menu: %v", err)
		}
		return
	}

	menu, err := menus.GenerateBoot(arch, token, vmID)
	if err != nil {
		log.Printf("error generating the boot menu: %v", err)
	}

	if _, err = fmt.Fprint(w, menu); err != nil {
		log.Printf("error writting the boot menu: %v", err)
	}
}

// VmlinuzHandler is the handler that serves the vmlinuz file for the boot
func VmlinuzHandler(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "images/"+r.FormValue("arch")+"/vmlinuz")
}

// InitrdHandler is the handler that serves the initrd file for the boot
func InitrdHandler(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "images/"+r.FormValue("arch")+"/initrd")
}
