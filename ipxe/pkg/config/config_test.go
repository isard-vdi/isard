package config_test

import (
	"math/rand"
	"os"
	"reflect"
	"testing"

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
	if err != nil {
		return err
	}

	return nil
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
	if err != nil {
		return err
	}

	return nil
}
func TestReadConfig(t *testing.T) {
	t.Run("reads the configuration successfully", func(t *testing.T) {
		if err := prepareTest(true); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		expectedConfig := &config.Config{
			BaseURL: "https://isard.domain.com",
			CACert:  "./certs/ca.pem",
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
}
