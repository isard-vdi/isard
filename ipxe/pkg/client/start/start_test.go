package start_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"reflect"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/client/start"
)

type startBody struct {
	Token string `json:"tkn"`
	Id    string `json:"id"`
}

type testWebRequest struct{}

func (testWebRequest) Get(url string) ([]byte, int, error) {
	return nil, 500, nil
}

func (testWebRequest) Post(url string, body io.Reader) ([]byte, int, error) {
	bodyBuf := new(bytes.Buffer)
	bodyBuf.ReadFrom(body)

	var decodedBuffer startBody

	err := json.Unmarshal(bodyBuf.Bytes(), &decodedBuffer)
	if err != nil {
		return nil, 500, fmt.Errorf("bad formatted body: %v", err)
	}

	var expectedRequest requestKey

	for _, currReq := range requests {
		if currReq.ReqBody.Token == decodedBuffer.Token && currReq.ReqBody.Id == decodedBuffer.Id {
			expectedRequest = currReq
		}
	}

	if reflect.DeepEqual(expectedRequest, requestKey{}) {
		return expectedRequest.Body, 404, errors.New("endpoint not found")
	}

	return expectedRequest.Body, expectedRequest.Code, expectedRequest.Err
}

var requests []requestKey

type requestKey struct {
	ReqBody startBody
	Body    []byte
	Code    int
	Err     error
}

var tests = []struct {
	validToken string
	vmID       string
	requests   []requestKey
}{
	{
		validToken: "zflUbbR_X6dclZ1gr7BPrrXN4NHTwWCvPsKe4zGWJDY",
		vmID:       "_nefix_Debian_9",
		requests: []requestKey{
			requestKey{
				ReqBody: startBody{
					Token: "zflUbbR_X6dclZ1gr7BPrrXN4NHTwWCvPsKe4zGWJDY",
					Id:    "_nefix_Debian_9",
				},
				Body: nil,
				Code: 200,
				Err:  nil,
			},
			requestKey{
				ReqBody: startBody{
					Token: "error",
					Id:    "_nefix_Debian_9",
				},
				Body: nil,
				Code: 500,
				Err:  errors.New("testing error"),
			},
			requestKey{
				ReqBody: startBody{
					Token: "unauthorized",
					Id:    "_nefix_Debian_9",
				},
				Body: nil,
				Code: 403,
				Err:  nil,
			},
			requestKey{
				ReqBody: startBody{
					Token: "vmfailed",
					Id:    "_nefix_Debian_9",
				},
				Body: []byte(`{
	"code": 2,
	"msg": "testing error"
}`),
				Code: 500,
				Err:  nil,
			},
			requestKey{
				ReqBody: startBody{
					Token: "vmfailedjson",
					Id:    "_nefix_Debian_9",
				},
				Body: []byte(`%ss3`),
				Code: 500,
				Err:  nil,
			},
		},
	},
}

func TestStart(t *testing.T) {
	for _, tt := range tests {
		requests = tt.requests

		t.Run("should work as expected", func(t *testing.T) {
			err := start.Call(testWebRequest{}, tt.validToken, tt.vmID)
			if err != nil {
				t.Errorf("unexpected error: %v", err)
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

			expectedErr := "open config.yml: permission denied"

			err = start.Call(testWebRequest{}, tt.validToken, tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %s, but got %v", expectedErr, err)
			}

			err = os.Chdir(initialFolder)
			if err != nil {
				t.Fatalf("error finishing the test %v", err)
			}
		})

		t.Run("there's an error calling the API", func(t *testing.T) {
			expectedErr := "testing error"

			err := start.Call(testWebRequest{}, "error", tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}
		})

		t.Run("the code is not 200", func(t *testing.T) {
			expectedErr := "HTTP Code: 403"

			err := start.Call(testWebRequest{}, "unauthorized", tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}
		})

		t.Run("the code is 500", func(t *testing.T) {
			expectedErr := "VM start failed: testing error"

			err := start.Call(testWebRequest{}, "vmfailed", tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}
		})

		t.Run("the code is 500 and there's an error decoding the JSON body", func(t *testing.T) {
			expectedErr := "invalid character '%' looking for beginning of value"

			err := start.Call(testWebRequest{}, "vmfailedjson", tt.vmID)
			if err.Error() != expectedErr {
				t.Errorf("expecting %v, but got %v", expectedErr, err)
			}
		})

		t.Run("there's an error encoding the JSON body", func(t *testing.T) {
		})
	}

	// Clean the generated configuration file
	err := os.Remove("config.yml")
	if err != nil {
		t.Fatalf("error finishing the tests: %v", err)
	}
}
