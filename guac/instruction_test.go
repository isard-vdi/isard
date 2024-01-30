package guac

import (
	"testing"
	"time"
)

func TestInstruction_String(t *testing.T) {
	ins := NewInstruction("select", "hi", "hello", "asdf")
	if ins.String() != "6.select,2.hi,5.hello,4.asdf;" {
		t.Error("Unexpected result:", ins.String())
	}
	if ins.String() != "6.select,2.hi,5.hello,4.asdf;" {
		t.Error("Unexpected result:", ins.String())
	}

	ins = NewInstruction(InternalDataOpcode, "hi", "hello", "asdf")
	if ins.String() != "0.,2.hi,5.hello,4.asdf;" {
		t.Error("Unexpected result:", ins.String())
	}
	if ins.String() != "0.,2.hi,5.hello,4.asdf;" {
		t.Error("Unexpected result:", ins.String())
	}
}

func TestReadOne(t *testing.T) {
	stream := NewStream(&fakeConn{
		ToRead: []byte(`6.select,2.hi,5.hello,4.asdf;6.select,2.hi,5.hello,4.asdf;`),
	}, time.Minute)

	ins, err := ReadOne(stream)
	if err != nil {
		t.Fatal(err)
	}

	if ins.String() != "6.select,2.hi,5.hello,4.asdf;" {
		t.Error("Unexpected", ins.String())
	}
}
