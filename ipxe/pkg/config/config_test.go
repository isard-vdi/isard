package config_test

import (
	"io/ioutil"
	"os"
	"reflect"
	"testing"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

func TestReadConfig(t *testing.T) {
	t.Run("reads the configuration successfully", func(t *testing.T) {
		expectedConfig := &config.Config{
			BaseURL:   "https://isard.domain.com",
			BuildsURL: "https://builds.isardvdi.com",
			CACert:    "./certs/server-cert.pem",
		}

		config := &config.Config{}
		if err := config.ReadConfig(); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %s, but got %s", expectedConfig, config)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("create initial config fails", func(t *testing.T) {
		initialFolder, err := os.Getwd()
		if err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		if err = os.Chdir("/"); err != nil {
			t.Fatalf("error preparing the test %v", err)
		}

		expectedConfig := &config.Config{}

		config := &config.Config{}
		if err = config.ReadConfig(); !os.IsPermission(err) {
			t.Errorf("expecting %v, but got %v", os.ErrPermission, err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %v, but git %v", expectedConfig, config)
		}

		if err := os.Chdir(initialFolder); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("there's an error reading the configuration file", func(t *testing.T) {
		config := config.Config{}
		if err := config.ReadConfig(); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		if err := os.Chmod("config.yml", 0000); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "open config.yml: permission denied"

		if err := config.ReadConfig(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("there's an error parsing the YAML", func(t *testing.T) {
		if err := ioutil.WriteFile("config.yml", []byte(`%&'
:;|[]()`), 0644); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "yaml: could not find expected directive name"

		config := &config.Config{}
		if err := config.ReadConfig(); err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("if the file is empty, write the configuration ", func(t *testing.T) {
		if err := ioutil.WriteFile("config.yml", []byte{}, 0644); err != nil {
			t.Fatalf("error preparing the test")
		}

		expectedConfig := &config.Config{
			BaseURL:   "https://isard.domain.com",
			BuildsURL: "https://builds.isardvdi.com",
			CACert:    "./certs/server-cert.pem",
		}

		config := &config.Config{}
		if err := config.ReadConfig(); err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %s, but got %s", expectedConfig, config)
		}

		if err := os.Remove("config.yml"); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})
}
