package list

import (
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/pkg/api/mocks"
	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// VMList is the complete response of the API
type VMList struct {
	VMs []*VM `json:"vms"`
}

// VM is an individual Virtual Machine
type VM struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

// Call calls the Isard API and returns a list of all the VMs of a specific user
func Call(webRequest mocks.WebRequest, token string) (*VMList, error) {
	config := config.Config{}

	err := config.ReadConfig()
	if err != nil {
		return &VMList{}, err
	}

	url := config.BaseURL + "/pxe/list?tkn=" + token

	body, code, err := webRequest.Get(url)
	if err != nil {
		return &VMList{}, err

	} else if code != 200 {
		return &VMList{}, fmt.Errorf("HTTP Code: %d", code)
	}

	listVMsResponse := &VMList{}

	err = json.Unmarshal(body, &listVMsResponse)
	if err != nil {
		return &VMList{}, err
	}

	return listVMsResponse, nil
}
