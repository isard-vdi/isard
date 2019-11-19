package guac

import (
	"testing"
	"time"
)

func TestTunnelMap(t *testing.T) {
	tmap := TunnelMap{
		tunnelMap:     make(map[string]*LastAccessedTunnel),
		tunnelTimeout: time.Millisecond,
	}

	tunnel, ok := tmap.Get("1")
	if tunnel != nil || ok {
		t.Error("Expected not to find anything, found", tunnel, ok)
	}

	ft := &fakeTunnel{}
	tmap.Put("1", ft)

	tunnel, ok = tmap.Get("1")
	if tunnel == nil || !ok {
		t.Error("Expected to find tunnel but found", tunnel, ok)
	}

	tmap.tunnelTimeoutTaskRun()

	tunnel, ok = tmap.Get("1")
	if tunnel == nil || !ok {
		t.Error("Expected to find tunnel but found", tunnel, ok)
	}

	time.Sleep(time.Millisecond)

	tmap.tunnelTimeoutTaskRun()
	tunnel, ok = tmap.Get("1")
	if tunnel != nil || ok {
		t.Error("Expected tunnel to have been removed but found", tunnel, ok)
	}
}
