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

package login_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"reflect"
	"regexp"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/api/login"
)

type loginBody struct {
	Username string `json:"usr"`
	Password string `json:"pwd"`
}

type requestKey struct {
	ReqBody loginBody
	Body    []byte
	Code    int
	Err     error
}

type testWebRequest struct{}

func (testWebRequest) Get(url string) ([]byte, int, error) {
	return nil, 500, nil
}

func (testWebRequest) Post(url string, body io.Reader) ([]byte, int, error) {
	bodyBuf := new(bytes.Buffer)
	bodyBuf.ReadFrom(body)

	var decodedBuffer loginBody

	err := json.Unmarshal(bodyBuf.Bytes(), &decodedBuffer)
	if err != nil {
		return nil, 500, fmt.Errorf("bad formatted body: %v", err)
	}

	var expectedRequest requestKey

	for _, currReq := range requests {
		if currReq.ReqBody.Username == decodedBuffer.Username && currReq.ReqBody.Password == decodedBuffer.Password {
			expectedRequest = currReq
		}
	}

	if reflect.DeepEqual(expectedRequest, requestKey{}) {
		return expectedRequest.Body, 404, errors.New("endpoint not found")
	}

	return expectedRequest.Body, expectedRequest.Code, expectedRequest.Err
}

var requests []requestKey

var tests = []struct {
	username string
	password string
	token    string
	requests []requestKey
}{
	{
		username: "nefix",
		password: "p4$$w0rd!",
		token:    "yHZe21Squ2ZjRYKQOE81vU5llRjWj3nPpiZv4pQQTkU",
		requests: []requestKey{
			requestKey{
				ReqBody: loginBody{
					Username: "nefix",
					Password: "p4$$w0rd!",
				},
				Body: []byte(`{
					"tkn": "yHZe21Squ2ZjRYKQOE81vU5llRjWj3nPpiZv4pQQTkU"
				}`),
				Code: 200,
				Err:  nil,
			},
			requestKey{
				ReqBody: loginBody{
					Username: "error",
					Password: "p4$$w0rd!",
				},
				Body: []byte(`{}`),
				Err:  errors.New("testing error"),
			},
			requestKey{
				ReqBody: loginBody{
					Username: "invaliduser",
					Password: "p4$$w0rd!",
				},
				Body: []byte(`{
					"tkn": "yHZe21Squ2ZjRYKQOE81vU5llRjWj3nPpiZv4pQQTkU"
				}`),
				Code: 403,
				Err:  nil,
			},
			requestKey{
				ReqBody: loginBody{
					Username: "invalidjson",
					Password: "p4$$w0rd!",
				},
				Body: []byte(`not json!`),
				Code: 200,
				Err:  nil,
			},
		},
	},
}

func TestLogin(t *testing.T) {
	for _, tt := range tests {
		requests = tt.requests

		t.Run("should work as expected", func(t *testing.T) {
			expectedRsp := tt.token

			token, err := login.Call(testWebRequest{}, tt.username, tt.password)
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}

			if !reflect.DeepEqual(token, expectedRsp) {
				t.Errorf("expecting %v, but got %v", expectedRsp, token)
			}
		})

		t.Run("there's an error reading the configuration", func(t *testing.T) {
			initialFolder, err := os.Getwd()
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			err = os.Chdir("/")
			if err != nil {
				t.Fatalf("error preparing the test %v", err)
			}

			expectedRsp := ""
			expectedErr := "open config.yml: permission denied"

			token, err := login.Call(testWebRequest{}, tt.username, tt.password)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if token != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, token)
			}

			err = os.Chdir(initialFolder)
			if err != nil {
				t.Fatalf("error finishing the test %v", err)
			}
		})

		t.Run("there's an error calling the API", func(t *testing.T) {
			expectedRsp := ""
			expectedErr := "testing error"

			token, err := login.Call(testWebRequest{}, "error", tt.password)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}

			if expectedRsp != token {
				t.Errorf("expecting %s, but got %s", expectedRsp, token)
			}
		})

		t.Run("the code is not 200", func(t *testing.T) {
			expectedRsp := ""
			expectedErr := "HTTP Code: 403"

			token, err := login.Call(testWebRequest{}, "invaliduser", tt.password)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}

			if token != expectedRsp {
				t.Errorf("expecting %s, but got %s", expectedRsp, token)
			}
		})

		t.Run("error encoding the request body", func(t *testing.T) {

		})

		t.Run("error decoding the response body", func(t *testing.T) {
			expectedRsp := ""
			expectedErr := "^invalid character '.' in literal null \\(expecting '.'\\)$"

			token, err := login.Call(testWebRequest{}, "invalidjson", tt.password)
			matched, rErr := regexp.MatchString(expectedErr, err.Error())
			if rErr != nil {
				t.Fatalf("error matching regex: %v", rErr)
			}

			if !matched {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			if token != expectedRsp {
				t.Errorf("expecting %v, but got %v", expectedRsp, token)
			}
		})
	}

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
