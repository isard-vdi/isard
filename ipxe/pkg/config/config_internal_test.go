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

package config

import (
	"bytes"
	"io/ioutil"
	"os"
	"testing"
)

func TestCreateInitialConfig(t *testing.T) {
	t.Run("creates the configuration file correctly", func(t *testing.T) {
		expectedConfig := []byte(`base_url: https://isard.domain.com
builds_url: https://builds.isardvdi.com
ca_cert: ./certs/server-cert.pem
`)

		err := createInitialConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		f, err := ioutil.ReadFile("config.yml")
		if err != nil {
			t.Fatalf("error during the test: %v", err)
		}

		if !bytes.Equal(expectedConfig, f) {
			t.Errorf("expecting %s, but got %s", expectedConfig, f)
		}

		if err = os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("error creating the file", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		if err = os.Chdir("/"); err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		if err := createInitialConfig(); !os.IsPermission(err) {
			t.Errorf("expected %v, but got %v", os.ErrPermission, err)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}
