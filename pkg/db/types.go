package db

import (
	"reflect"
	"strings"
	"time"

	"gopkg.in/rethinkdb/rethinkdb-go.v6/encoding"
)

type CommaSplitString []string

func (c CommaSplitString) MarshalRQL() (any, error) {
	return strings.Join(c, ","), nil
}

func (c *CommaSplitString) UnmarshalRQL(buf any) error {
	str, ok := buf.(string)
	if !ok {
		return &encoding.UnsupportedTypeError{
			Type: reflect.TypeOf(buf),
		}
	}
	if str == "" {
		*c = nil
		return nil
	}

	*c = strings.Split(str, ",")
	return nil
}

type Duration time.Duration

func (d Duration) MarshalRQL() (any, error) {
	return time.Duration(d).String(), nil
}

func (d *Duration) UnmarshalRQL(buf any) error {
	str, ok := buf.(string)
	if !ok {
		return &encoding.UnsupportedTypeError{
			Type: reflect.TypeOf(buf),
		}
	}

	dur, err := time.ParseDuration(str)
	if err != nil {
		return &encoding.DecodeTypeError{
			SrcType:  reflect.TypeOf(str),
			DestType: reflect.TypeOf(*d),
			Reason:   err.Error(),
		}
	}

	*d = Duration(dur)

	return nil
}
