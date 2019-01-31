package config

import (
	"bytes"
	"io/ioutil"
	"os"
	"testing"
)

func TestCreateInitialConfig(t *testing.T) {
	t.Run("creates the configuration file correctly", func(t *testing.T) {
		expectedConfig := []byte(`base_url: https://isard.domain.com
builds_url: https://builds.isardvdi.com
ca_cert: ./certs/server-cert.pem
`)

		err := createInitialConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		f, err := ioutil.ReadFile("config.yml")
		if err != nil {
			t.Fatalf("error during the test: %v", err)
		}

		if !bytes.Equal(expectedConfig, f) {
			t.Errorf("expecting %s, but got %s", expectedConfig, f)
		}

		if err = os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("error creating the file", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		if err = os.Chdir("/"); err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		if err := createInitialConfig(); !os.IsPermission(err) {
			t.Errorf("expected %v, but got %v", os.ErrPermission, err)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}
