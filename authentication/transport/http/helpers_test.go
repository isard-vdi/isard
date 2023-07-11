package http

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseArgs(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Request      func() *http.Request
		ExpectedArgs map[string]string
		ExpectedErr  string
	}{
		"should parse the GET arguments correctly": {
			Request: func() *http.Request {
				return httptest.NewRequest(http.MethodGet, "/?argument_test=value&argument_with_no_value", nil)
			},
			ExpectedArgs: map[string]string{
				"argument_test":          "value",
				"argument_with_no_value": "",
				"request_body":           "",
				"token":                  "",
			},
		},
		"should parse the POST arguments correctly": {
			Request: func() *http.Request {
				data := url.Values{}
				data.Add("argument_test", "value")

				req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(data.Encode()))
				req.Header.Add("Content-Type", "application/x-www-form-urlencoded")

				return req
			},
			ExpectedArgs: map[string]string{
				"argument_test": "value",
				"request_body":  "",
				"token":         "",
			},
		},
		"should parse the JSON arguments correctly": {
			Request: func() *http.Request {
				data := `{"provider": "local","category_id":"default","argument_test": "value","another_value": "testing"}`

				return httptest.NewRequest(http.MethodPost, "/", strings.NewReader(data))
			},
			ExpectedArgs: map[string]string{
				"provider":     "local",
				"category_id":  "default",
				"request_body": `{"provider": "local","category_id":"default","argument_test": "value","another_value": "testing"}`,
				"token":        "",
			},
		},
		"should parse GET parameters with a POST request": {
			Request: func() *http.Request {
				return httptest.NewRequest(http.MethodPost, "/?argument_test=value&argument_with_no_value", nil)
			},
			ExpectedArgs: map[string]string{
				"argument_test":          "value",
				"argument_with_no_value": "",
				"request_body":           "",
				"token":                  "",
			},
		},
	}

	for name, tt := range cases {
		t.Run(name, func(t *testing.T) {
			args, err := parseArgs(tt.Request())

			assert.Equal(tt.ExpectedArgs, args)

			if tt.ExpectedErr == "" {
				assert.NoError(err)
			} else {
				assert.EqualError(err, tt.ExpectedErr)
			}
		})
	}
}
