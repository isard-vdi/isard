package storage

import (
	"errors"

	"github.com/spf13/afero"
)

func New(driver string) (afero.Fs, error) {
	switch driver {
	case "os":
		return afero.NewOsFs(), nil
	}

	return nil, errors.New("unknown storage driver")
}
