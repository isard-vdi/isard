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

package cert_test

import (
	"fmt"
	"io/ioutil"
	"os"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/cert"
	"github.com/isard-vdi/isard-ipxe/pkg/config"

	yaml "gopkg.in/yaml.v2"
)

// updateBaseURL changes the BaseURL of the configuration
func updateBaseURL(url string) error {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		return fmt.Errorf("error reading the configuration file: %v", err)
	}

	config.BaseURL = url

	b, err := yaml.Marshal(config)
	if err != nil {
		return err
	}

	err = ioutil.WriteFile("config.yml", b, 0600)

	return err
}

func TestCheck(t *testing.T) {
	t.Run("should work as expected: the certificate is valid", func(t *testing.T) {
		cert.IsValid = false

		err := updateBaseURL("https://fsf.org")
		if err != nil {
			t.Fatal(err)
		}

		err = cert.Check()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !cert.IsValid {
			t.Errorf("the IsValid variable is false")
		}
	})

	t.Run("should work as expected: the certificate isn't valid", func(t *testing.T) {
		cert.IsValid = true

		err := updateBaseURL("https://self-signed.badssl.com/")
		if err != nil {
			t.Fatal(err)
		}

		err = cert.Check()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if cert.IsValid {
			t.Errorf("the IsValid variable is true")
		}
	})

	t.Run("error checking the domain certificate", func(t *testing.T) {
		cert.IsValid = true

		err := updateBaseURL("https://ufhwuifhwuiehfweuihwirhwefw.efwef.wefuiowehfiweuhfweuifhweui")
		if err != nil {
			t.Fatal(err)
		}

		expectedErr := "error checking the certificate: Get https://ufhwuifhwuiehfweuihwirhwefw.efwef.wefuiowehfiweuhfweuifhweui: dial tcp: lookup ufhwuifhwuiehfweuihwirhwefw.efwef.wefuiowehfiweuhfweuifhweui: no such host"

		err = cert.Check()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if cert.IsValid {
			t.Errorf("the IsValid variable is true")
		}
	})

	t.Run("error reading the configuration file", func(t *testing.T) {
		cert.IsValid = true

		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		err = os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		expectedErr := "error checking the certificate: open config.yml: permission denied"

		err = cert.Check()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if cert.IsValid {
			t.Errorf("the IsValid variable is true")
		}

		err = os.Chdir(initialFolder)
		if err != nil {
			t.Fatalf("error finishing the test %v", err)
		}
	})

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
