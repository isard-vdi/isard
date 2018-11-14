package config

import (
	"math/rand"
	"os"
	"testing"
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

func TestCreateInitialConfig(t *testing.T) {
	t.Run("creates the configuration file correctly", func(t *testing.T) {
		if err := prepareTest(true); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		err := createInitialConfig()
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if err = finishTest(true); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}
	})

	t.Run("error creating the file", func(t *testing.T) {
		var err error

		if err = prepareTest(false, "/"); err != nil {
			t.Fatalf("error preparing the test: %v", err)
		}

		err = createInitialConfig()
		if !os.IsPermission(err) {
			t.Errorf("expected %v, but got %v", os.ErrPermission, err)
		}

		if err = finishTest(false); err != nil {
			t.Fatalf("error finishing the test: %v", err)
		}

	})
}
