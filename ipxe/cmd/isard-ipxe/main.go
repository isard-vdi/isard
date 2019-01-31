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

package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/isard-vdi/isard-ipxe/pkg/cert"
	"github.com/isard-vdi/isard-ipxe/pkg/downloads"
	"github.com/isard-vdi/isard-ipxe/pkg/handlers"
)

type logWriter struct {
	File *os.File
}

func (w *logWriter) Write(b []byte) (int, error) {
	fmt.Print(string(b[:]))

	return w.File.Write(b)
}

func generateMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/", handlers.LoginHandler)
	mux.HandleFunc("/pxe/boot/auth", handlers.AuthHandler)
	mux.HandleFunc("/pxe/boot/list", handlers.VMListHandler)
	mux.HandleFunc("/pxe/boot/start", handlers.StartHandler)
	mux.HandleFunc("/pxe/boot/vmlinuz", handlers.VmlinuzHandler)
	mux.HandleFunc("/pxe/boot/initrd", handlers.InitrdHandler)

	return mux
}

func main() {
	// Configure the logging
	f, err := os.OpenFile("isard-ipxe.log", os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err != nil {
		log.Fatalf("error opening log file: %v", err)
	}
	defer func() {
		if err = f.Close(); err != nil {
			log.Fatalf("error closing the log file: %v", err)
		}
	}()

	w := &logWriter{
		File: f,
	}

	log.SetOutput(w)

	// Generate the router
	mux := generateMux()

	// Check the certificate
	err = cert.Check()
	if err != nil {
		log.Fatal(err)
	}

	// Download all the images
	if err := downloads.CreateImagesDirectories(); err != nil {
		log.Fatal(err)
	}

	if _, err := os.Stat(filepath.Join("images", ".downloaded")); err != nil {
		if os.IsNotExist(err) {
			log.Println("Downloading images... Please be patient")
			if err := downloads.DownloadImages(); err != nil {
				log.Println(err)
			}
		} else {
			log.Fatalf("error reading the downloads check file: %v", err)
		}
	}
	// Start the server
	log.Println("Starting to listen at port :3000")
	if err := http.ListenAndServe(":3000", mux); err != nil {
		log.Fatalf("error listening the server: %v", err)
	}
}
