package guac

import (
	"strings"
	"testing"
	"time"
)

func relayOutcomes(t *testing.T, stream string) []Outcome {
	t.Helper()
	var got []Outcome
	conn := &fakeConn{ToRead: []byte(strings.ReplaceAll(stream, "\n", ""))}
	guacdToWs(&fakeMessageWriter{}, NewStream(conn, time.Minute), func(o Outcome) { got = append(got, o) })
	return got
}

func TestOutcomeIsTheGuestErrorEvenAfterTheClientLooksConnected(t *testing.T) {
	got := relayOutcomes(t, `5.ready,37.$00000000-0000-0000-0000-000000000000;
4.sync,1.1,1.0;
5.error,48.Server refused connection (wrong security type?),3.519;`)

	if len(got) != 1 || got[0].Connected || got[0].Code != 519 ||
		got[0].Message != "Server refused connection (wrong security type?)" {
		t.Fatalf("unexpected outcomes %+v", got)
	}
}

func TestOutcomeIsConnectedOnceTheDefaultLayerIsSized(t *testing.T) {
	got := relayOutcomes(t, `5.ready,37.$00000000-0000-0000-0000-000000000000;
4.size,2.-2,2.32,2.32;
4.size,1.0,4.1024,3.768;
5.error,19.Manually logged off,3.512;`)

	if len(got) != 1 || !got[0].Connected {
		t.Fatalf("unexpected outcomes %+v", got)
	}
}

func TestNoOutcomeWithoutAnError(t *testing.T) {
	if got := relayOutcomes(t, `4.sync,1.1,1.0;`); len(got) != 0 {
		t.Fatalf("unexpected outcomes %+v", got)
	}
}
