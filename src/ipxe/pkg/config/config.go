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

	yaml "gopkg.in/yaml.v2"
)

// Config is the struct that contains all the configuration parameters
type Config struct {
	BaseURL string `yaml:"base_url"`

	// BuildsURL is the URL of the Isard Builder from which Isard iPXE is going to download all the images and compile the iPXE binaries
	BuildsURL string `yaml:"builds_url"`

	// TLS Certificates
	CACert string `yaml:"ca_cert"`
}

// createInitialConfig creates the configuration file and populates it with the default values
func createInitialConfig() error {
	c := &Config{
		BaseURL:   "https://isard.domain.com",
		BuildsURL: "https://builds.isardvdi.com",
		CACert:    "./certs/server-cert.pem",
	}

	d, err := yaml.Marshal(c)
	if err != nil {
		return err
	}

	err = ioutil.WriteFile("config.yml", d, 0644)
	return err
}

// ReadConfig reads the configuration
func (c *Config) ReadConfig() error {
	if _, err := os.Stat("config.yml"); os.IsNotExist(err) {
		if err = createInitialConfig(); err != nil {
			return err
		}
	}

	yamlFile, err := ioutil.ReadFile("config.yml")
	if err != nil {
		return err
	}

	if bytes.Equal(yamlFile, []byte{}) {
		if err = createInitialConfig(); err != nil {
			return err
		}

		yamlFile, err = ioutil.ReadFile("config.yml")
		if err != nil {
			return err
		}
	}

	err = yaml.Unmarshal(yamlFile, c)

	return err
}
