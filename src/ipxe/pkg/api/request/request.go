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

package request

import (
	"crypto/tls"
	"crypto/x509"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"strings"

	"github.com/isard-vdi/isard-ipxe/pkg/cert"
	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// createClient creates the client that is going to be used when calling the API for both GET and POST
func createClient() (*http.Client, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		return nil, err
	}

	var client = &http.Client{}

	protocol := strings.Split(config.BaseURL, ":")[0]
	if protocol == "https" && !cert.IsValid {
		caCert, err := ioutil.ReadFile(config.CACert)
		if err != nil {
			return nil, err
		}

		rootCAs := x509.NewCertPool()
		rootCAs.AppendCertsFromPEM(caCert)

		tlsConfig := &tls.Config{
			RootCAs: rootCAs,
		}

		client.Transport = &http.Transport{TLSClientConfig: tlsConfig}
	}

	return client, nil
}

// Request is the struct that implements mocks.WebRequest
type Request struct{}

// Get makes a GET call to the specified url. If there's no error calling the API, error will be nil;
// even if the status code is 500
func (r Request) Get(url string) (body []byte, code int, err error) {
	client, err := createClient()
	if err != nil {
		return nil, 0, err
	}

	rsp, err := client.Get(url)
	if err != nil {
		return nil, 0, err
	}
	defer func() {
		if err = rsp.Body.Close(); err != nil {
			log.Printf("error closing the response body: %s", url)
		}
	}()

	body, err = ioutil.ReadAll(rsp.Body)
	if err != nil {
		return nil, 0, err
	}

	return body, rsp.StatusCode, nil
}

// Post makes a POST call tot he specified url. If there's no error calling the API, error will be nil;
// even if the status code is 500
func (r Request) Post(url string, body io.Reader) ([]byte, int, error) {
	client, err := createClient()
	if err != nil {
		return nil, 0, err
	}

	rsp, err := client.Post(url, "application/json", body)
	if err != nil {
		return nil, 0, err
	}
	defer func() {
		if err = rsp.Body.Close(); err != nil {
			log.Printf("error closing the response body: %s", url)
		}
	}()

	rspBody, err := ioutil.ReadAll(rsp.Body)
	if err != nil {
		return nil, 0, err
	}

	return rspBody, rsp.StatusCode, nil
}
