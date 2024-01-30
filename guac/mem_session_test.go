package guac

import "testing"

func TestMemorySessionStore(t *testing.T) {
	sessions := NewMemorySessionStore()

	if sessions.Get("1") != 0 {
		t.Errorf("Expected 0 got %d", sessions.Get("1"))
	}

	sessions.Add("1", nil)

	if sessions.Get("1") != 1 {
		t.Errorf("Expected 1 got %d", sessions.Get("1"))
	}

	sessions.Add("1", nil)

	if sessions.Get("1") != 2 {
		t.Errorf("Expected 2 got %d", sessions.Get("1"))
	}

	sessions.Delete("1", nil, nil)

	if sessions.Get("1") != 1 {
		t.Errorf("Expected 1 got %d", sessions.Get("1"))
	}

	sessions.Delete("1", nil, nil)

	if sessions.Get("1") != 0 {
		t.Errorf("Expected 0 got %d", sessions.Get("1"))
	}
}
