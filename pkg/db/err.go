package db

import (
	"fmt"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Err struct {
	Msg string
	Err error
}

func (e *Err) Error() string {
	if e == nil {
		return ""
	}

	if e.Msg == "" {
		return e.Err.Error()
	}

	return fmt.Sprintf("%s: %s", e.Msg, e.Err)
}

func (e *Err) Is(target error) bool {
	if e == nil {
		return false
	}

	t, ok := target.(*Err)
	if !ok {
		return false
	}

	return t.Msg == e.Msg && t.Err.Error() == e.Err.Error()
}

func (e *Err) Unwrap() error {
	if e == nil {
		return nil
	}

	return e.Err
}

var (
	ErrNotFound = &Err{
		Msg: "not found",
		Err: r.ErrEmptyResult,
	}
)
