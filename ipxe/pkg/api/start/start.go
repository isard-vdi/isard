package start

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
	"github.com/isard-vdi/isard-ipxe/pkg/mocks"
)

type body struct {
	Token string `json:"tkn"`
	ID    string `json:"id"`
}

// Call calls the Isard API and starts a VM
func Call(webRequest mocks.WebRequest, token string, vmID string) error {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return err
	}

	url := config.BaseURL + "/pxe/start"

	encodedBody, err := json.Marshal(body{
		Token: token,
		ID:    vmID,
	})
	if err != nil {
		return err
	}

	body := bytes.NewBuffer(encodedBody)

	rspBody, code, err := webRequest.Post(url, body)
	if err != nil {
		return err
	}

	if code != 200 {
		if code == 500 {
			type err500 struct {
				Code    int    `json:"code"`
				Message string `json:"msg"`
			}

			rspErr := &err500{}

			err = json.Unmarshal(rspBody, rspErr)
			if err != nil {
				return err
			}

			if rspErr.Code == 2 {
				return fmt.Errorf("VM start failed: %s", rspErr.Message)
			}
		}

		return fmt.Errorf("HTTP Code: %d", code)
	}

	return nil
}
