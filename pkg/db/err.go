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
	if e.Msg == "" {
		return e.Err.Error()
	}

	return fmt.Sprintf("%s: %s", e.Msg, e.Err)
}

func (e *Err) Is(target error) bool {
	t, ok := target.(*Err)
	if !ok {
		return false
	}

	return t.Msg == e.Msg && t.Err.Error() == e.Err.Error()
}

var (
	ErrNotFound = &Err{
		Msg: "not found",
		Err: r.ErrEmptyResult,
	}
)
