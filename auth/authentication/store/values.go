package store

import "time"

const (
	UsrIDStoreKey    = "id"
	ProviderStoreKey = "provider"
	TimeStoreKey     = "time"
)

type StoreValues struct {
	val map[interface{}]interface{}
}

func NewStoreValues(val map[interface{}]interface{}) *StoreValues {
	if val == nil {
		val = map[interface{}]interface{}{}
	}

	return &StoreValues{
		val: val,
	}
}

func (s *StoreValues) Len() int {
	return len(s.val)
}

func (s *StoreValues) SetUsrID(id string) {
	s.val[UsrIDStoreKey] = id
}

func (s *StoreValues) UsrID() string {
	return s.val[UsrIDStoreKey].(string)
}

func (s *StoreValues) SetProvider(p string) {
	s.val[ProviderStoreKey] = p
}

func (s *StoreValues) Provider() string {
	return s.val[ProviderStoreKey].(string)
}

func (s *StoreValues) SetTime(t time.Time) {
	s.val[TimeStoreKey] = t.Unix()
}

func (s StoreValues) Time() time.Time {
	return time.Unix(s.val[TimeStoreKey].(int64), 0)
}

func (s *StoreValues) Values() map[interface{}]interface{} {
	return s.val
}
