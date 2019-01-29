package login

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

type body struct {
	Username string `json:"usr"`
	Password string `json:"pwd"`
}

// Call tries to login using the Isard API and if it succeeds, returns a token
func Call(webRequest mocks.WebRequest, username string, password string) (string, error) {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return "", err
	}

	url := config.BaseURL + "/pxe/login"

	encodedBody, err := json.Marshal(body{
		Username: username,
		Password: password,
	})
	if err != nil {
		return "", err
	}

	body := bytes.NewBuffer(encodedBody)

	rsp, code, err := webRequest.Post(url, body)
	if err != nil {
		return "", err

	} else if code != 200 {
		return "", fmt.Errorf("HTTP Code: %d", code)
	}

	var token struct {
		Token string `json:"tkn"`
	}

	err = json.Unmarshal(rsp, &token)
	if err != nil {
		return "", err
	}

	return token.Token, nil
}
