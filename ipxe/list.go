package isardipxe

import (
	"encoding/json"
	"fmt"

	"github.com/isard-vdi/isard-ipxe/mocks"
)

// vmList is the complete response of the API
type vmList struct {
	VMs []*vm `json:"vms"`
}

// vm is an individual Virtual Machine
type vm struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

// listVMs calls the Isard API and returns a list of all the VMs of a specific user
func listVMs(webRequest mocks.WebRequest, token string) (*vmList, error) {
	config := config{}

	err := config.ReadConfig()
	if err != nil {
		return &vmList{}, err
	}

	url := config.BaseURL + "/pxe/list?tkn=" + token

	body, code, err := webRequest.Get(url)
	if err != nil {
		return &vmList{}, err

	} else if code != 200 {
		return &vmList{}, fmt.Errorf("HTTP Code: %d", code)
	}

	listVMsResponse := &vmList{}

	err = json.Unmarshal(body, &listVMsResponse)
	if err != nil {
		return &vmList{}, err
	}

	return listVMsResponse, nil
}
