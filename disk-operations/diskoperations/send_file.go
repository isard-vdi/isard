package diskoperations

import (
	"bytes"
	"context"
	"fmt"
	//"github.com/isard-vdi/isard/disk-operations/pkg/proto"
	//"github.com/snowzach/protosmart"
)

func (d *DiskOperations) SendFile(ctx context.Context, source string, destination string, file []bytes.Buffer) (bool, error) {
	//b, err := proto.Marshal(MyProtoBufType)
	//err = server.ServerStream.SendMsg(b)

	return false, fmt.Errorf("template not found")
}
