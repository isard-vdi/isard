package start

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/client/mocks"
	"github.com/isard-vdi/isard-ipxe/pkg/config"
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

	_, code, err := webRequest.Post(url, body)
	if err != nil {
		return err
	} else if code != 200 {
		return fmt.Errorf("HTTP Code: %d", code)
	}

	return nil
}
