package isardipxe

import (
	"math/rand"
	"os"
	"reflect"
	"testing"
)

var testingFolder string

func prepareTest() error {
	const letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

	b := make([]byte, 6)
	for i := range b {
		b[i] = letters[rand.Intn(len(letters))]
	}

	testingFolder = "/tmp/isard-ipxe_test_" + string(b)

	err := os.Mkdir(testingFolder, 0755)
	if err != nil {
		return err
	}

	err = os.Chdir(testingFolder)
	if err != nil {
		return err
	}

	return nil
}

func finishTest() error {
	err := os.RemoveAll(testingFolder)
	if err != nil {
		return err
	}

	return nil
}

func TestCreateInitialConfig(t *testing.T) {
	t.Run("creates the configuration file correctly", func(t *testing.T) {
		if err := prepareTest(); err != nil {
			t.Fatalf("error preparating the test: %v", err)
		}

		err := createInitialConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if err = finishTest(); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("error creating the file", func(t *testing.T) {
		err := os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparating the test: %v", err)
		}

		err = createInitialConfig()
		if !os.IsPermission(err) {
			t.Errorf("expected %v, but got %v", os.ErrPermission, err)
		}
	})
}

func TestReadConfig(t *testing.T) {
	t.Run("reads the configuration successfully", func(t *testing.T) {
		if err := prepareTest(); err != nil {
			t.Fatalf("error preparating the test: %v", err)
		}

		expectedConfig := &config{
			BaseURL: "https://isard.domain.com",
		}

		config := &config{}
		err := config.ReadConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %s, but got %s", expectedConfig, config)
		}

		if err = finishTest(); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("create initial config fails", func(t *testing.T) {
		err := os.Chdir("/")
		if err != nil {
			t.Fatalf("error preparating the test: %v", err)
		}

		expectedConfig := &config{}

		config := &config{}
		err = config.ReadConfig()
		if !os.IsPermission(err) {
			t.Errorf("expecting %v, but got %v", os.ErrPermission, err)
		}

		if !reflect.DeepEqual(config, expectedConfig) {
			t.Errorf("expecting %v, but git %v", expectedConfig, config)
		}
	})
}
