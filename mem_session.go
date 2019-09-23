package guac

import (
	"net/http"
	"sync"
)

type MemorySessionStore struct {
	sync.RWMutex
	ConnIds map[string]int
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{
		ConnIds: map[string]int{},
	}
}

func (s *MemorySessionStore) Get(id string) int {
	s.RLock()
	defer s.RUnlock()
	return s.ConnIds[id]
}

func (s *MemorySessionStore) Add(id string, req *http.Request) int {
	s.Lock()
	defer s.Unlock()
	n, ok := s.ConnIds[id]
	if !ok {
		s.ConnIds[id] = 1
		return 1
	}
	n++
	s.ConnIds[id] = n
	return n
}

func (s *MemorySessionStore) Delete(id string) int {
	s.Lock()
	defer s.Unlock()
	n, ok := s.ConnIds[id]
	if !ok {
		return 0
	}
	if n == 1 {
		delete(s.ConnIds, id)
		return 0
	}
	s.ConnIds[id]--
	return n - 1
}
