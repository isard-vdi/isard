package isardvdi

import "fmt"

type Err struct {
	Err *string `json:"error,omitempty"`
	Msg *string `json:"msg,omitempty"`
}

func (e *Err) Error() string {
	code := ""
	if e.Err != nil {
		code = fmt.Sprintf("%v", *e.Err)
	}

	msg := GetString(e.Msg)

	return fmt.Sprintf("%s: %s", code, msg)
}

func (e *Err) Is(target error) bool {
	t, ok := target.(*Err)
	if !ok {
		return false
	}

	return GetString(e.Err) == GetString(t.Err) && GetString(e.Msg) == GetString(t.Msg)
}

var (
	errNotFoundErr = "not_found"
	errNotFoundMsg = "Not found"
	ErrNotFound    = &Err{
		Err: &errNotFoundErr,
		Msg: &errNotFoundMsg,
	}

	errForbiddenErr = "forbidden"
	errForbiddenMsg = "Forbidden"
	ErrForbidden    = &Err{
		Err: &errForbiddenErr,
		Msg: &errForbiddenMsg,
	}
)
