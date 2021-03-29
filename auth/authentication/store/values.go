package store

import "time"

const (
	UsrIDStoreKey    = "id"
	UsrUUIDStoreKey  = "uuid"
	EntityIDStoreKey = "entity_id"
	ProviderStoreKey = "provider"
	TimeStoreKey     = "time"
)

type Values struct {
	val map[interface{}]interface{}
}

func NewValues(val map[interface{}]interface{}) *Values {
	if val == nil {
		val = map[interface{}]interface{}{}
	}

	return &Values{
		val: val,
	}
}

func (s *Values) Len() int {
	return len(s.val)
}

func (s *Values) SetUsrUUID(id string) {
	s.val[UsrUUIDStoreKey] = id
}

func (s *Values) SetUsrID(id int) {
	s.val[UsrIDStoreKey] = id
}

func (s *Values) UsrID() int {
	return s.val[UsrIDStoreKey].(int)
}

func (s *Values) UsrUUID() string {
	return s.val[UsrUUIDStoreKey].(string)
}

func (s *Values) SetEntityID(id int) {
	s.val[EntityIDStoreKey] = id
}

func (s *Values) EntityID() int {
	return s.val[EntityIDStoreKey].(int)
}

func (s *Values) SetProvider(p string) {
	s.val[ProviderStoreKey] = p
}

func (s *Values) Provider() string {
	return s.val[ProviderStoreKey].(string)
}

func (s *Values) SetTime(t time.Time) {
	s.val[TimeStoreKey] = t.Unix()
}

func (s Values) Time() time.Time {
	return time.Unix(s.val[TimeStoreKey].(int64), 0)
}

func (s *Values) Values() map[interface{}]interface{} {
	return s.val
}
