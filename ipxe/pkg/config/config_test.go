package config_test

import (
	"io/ioutil"
	"math/rand"
	"os"
	"reflect"
	"testing"
	"time"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

var initialFolder string
var testingFolder string

func prepareTest(workOnTmp bool, workDir ...string) error {
	var err error
	initialFolder, err = os.Getwd()
	if err != nil {
		return err
	}

	if workOnTmp {
		const letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

		b := make([]byte, 6)
		for i := range b {
			b[i] = letters[rand.Intn(len(letters))]
		}

		testingFolder = "/tmp/isard-ipxe_test_" + string(b)

		err = os.Mkdir(testingFolder, 0755)
		if err != nil {
			return err
		}

		workDir = make([]string, 1)
		workDir[0] = testingFolder
	}

	err = os.Chdir(workDir[0])
	return err
}

func finishTest(workOnTmp bool) error {
	var err error

	if workOnTmp {
		err = os.RemoveAll(testingFolder)
		if err != nil {
			return err
		}
	}

	err = os.Chdir(initialFolder)
	return err
}

func TestReadConfig(t *testing.T) {
	rand.Seed(time.Now().UTC().UnixNano())

	t.Run("reads the configuration successfully", func(t *testing.T) {
		if err := prepareTest(true); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedConfig := &config.Config{
			BaseURL:   "https://isard.domain.com",
			BuildsURL: "https://builds.isardvdi.com",
			CACert:    "./certs/server-cert.pem",
		}

		config := &config.Config{}
		err := config.ReadConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %s, but got %s", expectedConfig, config)
		}

		if err = finishTest(true); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("create initial config fails", func(t *testing.T) {
		var err error

		if err = prepareTest(false, "/"); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedConfig := &config.Config{}

		config := &config.Config{}
		err = config.ReadConfig()
		if !os.IsPermission(err) {
			t.Errorf("expecting %v, but got %v", os.ErrPermission, err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %v, but git %v", expectedConfig, config)
		}

		if err = finishTest(false); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("there's an error reading the configuration file", func(t *testing.T) {
		if err := prepareTest(true); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		config := config.Config{}
		err := config.ReadConfig()
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		err = os.Chmod("config.yml", 0000)
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "open config.yml: permission denied"

		err = config.ReadConfig()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err = finishTest(true); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("there's an error parsing the YAML", func(t *testing.T) {
		if err := prepareTest(true); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		config := config.Config{}
		err := config.ReadConfig()
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		err = ioutil.WriteFile("config.yml", []byte(`%&'
:;|[]()`), 0644)
		if err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedErr := "yaml: could not find expected directive name"

		err = config.ReadConfig()
		if err.Error() != expectedErr {
			t.Errorf("expecting %s, but got %v", expectedErr, err)
		}

		if err = finishTest(true); err != nil {
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
