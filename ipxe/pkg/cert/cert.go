package cert

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// IsValid states if the server has already trusted CA or not. If it does, there's no need of the cert
var IsValid = false

// Check updates the IsValid variable
func Check() error {
	IsValid = true

	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		IsValid = false

		return fmt.Errorf("error checking the certificate: %v", err)
	}

	_, err = http.Get(config.BaseURL)
	if err != nil {
		// Check that the error is because a self signed certificate
		if strings.Split(err.Error(), ": ")[1] == "x509" {
			err = nil
		}

		IsValid = false
	}

	return err
}
