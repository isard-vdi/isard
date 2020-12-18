package provider

import (
	"errors"
	"net/http"
)

type FormProvider struct {
	LocalProvider *Local
}

func (f *FormProvider) Login(w http.ResponseWriter, r *http.Request) error {
	if err := f.LocalProvider.Login(w, r); err != nil {
		if !errors.Is(err, ErrInvalidCredentials) {
			return err
		}
	}

	panic("not implemented")
	// return nil
}
