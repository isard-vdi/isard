package log

import "github.com/rs/zerolog"

func NewModelStrArray(s []string) ModelStrArray {
	return ModelStrArray{s}
}

type ModelStrArray struct {
	s []string
}

func (s ModelStrArray) MarshalZerologArray(a *zerolog.Array) {
	for _, str := range s.s {
		a.Str(str)
	}
}

func NewModelMapStrInt(m map[string]int) ModelMapStrInt {
	return ModelMapStrInt{m}
}

type ModelMapStrInt struct {
	m map[string]int
}

func (m ModelMapStrInt) MarshalZerologObject(e *zerolog.Event) {
	for k, v := range m.m {
		e.Int(k, v)
	}
}
