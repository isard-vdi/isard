package model

import (
	"fmt"

	"github.com/go-faster/jx"
)

// MustJxRaw encodes a value as a jx.Raw JSON literal. Panics on encoding failure.
func MustJxRaw(v any) jx.Raw {
	var e jx.Encoder
	switch val := v.(type) {
	case string:
		e.Str(val)
	case bool:
		e.Bool(val)
	case int:
		e.Int(val)
	default:
		panic(fmt.Sprintf("MustJxRaw: unsupported type %T", v))
	}
	return jx.Raw(e.Bytes())
}
