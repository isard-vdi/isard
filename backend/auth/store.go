package auth

import "gitlab.com/isard/isardvdi/backend/auth/provider"

type StoreValues struct {
	val map[interface{}]interface{}
}

func NewStoreValues(val map[interface{}]interface{}) *StoreValues {
	return &StoreValues{
		val: val,
	}
}

func (s *StoreValues) Len() int {
	return len(s.val)
}

func (s *StoreValues) UsrID() string {
	return s.val[provider.UsrIDStoreKey].(string)
}

func (s *StoreValues) Provider() string {
	return s.val[provider.ProviderStoreKey].(string)
}
