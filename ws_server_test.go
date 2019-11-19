package guac

import (
	"bytes"
	"io"
	"strings"
	"testing"
	"time"
)

func TestWebsocketServer_guacdToWs(t *testing.T) {
	const expBytes = `5.audio,1.1,31.audio/L16;rate=44100,channels=2;
4.size,1.0,4.1024,3.768;
4.size,2.-1,2.11,2.16;
3.img,1.3,2.12,2.-1,9.image/png,1.0,1.0;
4.blob,1.3,232.iVBORw0KGgoAAAANSUhEUgAAAAsAAAAQCAYAAADAvYV+AAAABmJLR0QA/wD/AP+gvaeTAAAAYklEQVQokY2RQQ4AIQgDW+L/v9y9qCEsIJ4QZggoJAnDYwAwFQwASI4EO8FEMH95CRYTnfCDOyGFK6GEM6GFo7AqKI4sSSsCJH1X+roFkKdjueABX/On77lz2uGtr6pj9okfTeJQAYVaxnMAAAAASUVORK5CYII=;
3.end,1.3;
6.cursor,1.0,1.0,2.-1,1.0,1.0,2.11,2.16;`
	expected := []byte(strings.ReplaceAll(expBytes, "\n", ""))
	msgWriter := &fakeMessageWriter{
		Messages: [][]byte{},
	}
	conn := &fakeConn{
		ToRead: expected,
	}
	guac := NewStream(conn, time.Minute)

	guacdToWs(msgWriter, guac)

	if len(msgWriter.Messages) != 1 {
		t.Error("Expected 1 got", len(msgWriter.Messages))
	}

	if !bytes.Equal(expected, msgWriter.Messages[0]) {
		t.Error("Unexpected bytes", string(msgWriter.Messages[0]))
	}
}

type fakeMessageWriter struct {
	Messages [][]byte
}

func (f *fakeMessageWriter) WriteMessage(n int, buf []byte) error {
	f.Messages = append(f.Messages, buf)
	return nil
}

type fakeTunnel struct {
	reader InstructionReader
	writer io.Writer
}

func (f *fakeTunnel) ConnectionID() string {
	return "asdf"
}

func (f *fakeTunnel) AcquireReader() InstructionReader {
	return f.reader
}

func (f *fakeTunnel) ReleaseReader() {
	return
}

func (f *fakeTunnel) HasQueuedReaderThreads() bool {
	return false
}

func (f *fakeTunnel) AcquireWriter() io.Writer {
	return f.writer
}

func (f *fakeTunnel) ReleaseWriter() {
	return
}

func (f *fakeTunnel) HasQueuedWriterThreads() bool {
	return false
}

func (f *fakeTunnel) GetUUID() string {
	return "1"
}

func (f *fakeTunnel) Close() error {
	return nil
}
