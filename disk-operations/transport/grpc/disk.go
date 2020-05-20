package grpc

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path"

	"github.com/isard-vdi/isard/disk-operations/pkg/proto"

	"github.com/zchee/go-qcow2"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DiskOperationsServer) CreateDisk(ctx context.Context, req *proto.CreateDiskRequest) (*proto.CreateDiskResponse, error) {

	_, err := os.Stat(req.Filename)
	if err == nil {
		return &proto.CreateDiskResponse{Result: true}, nil
	}

	dir, _ := path.Split(req.Filename)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		err = os.Mkdir(dir, os.ModePerm)
		if err != nil {
			return &proto.CreateDiskResponse{Result: false}, status.Error(codes.PermissionDenied, err.Error())
		}
	}

	var format qcow2.DriverFmt
	switch req.Format {
	case proto.Fmt_FMT_QCOW2:
		format = qcow2.DriverQCow2

	case proto.Fmt_FMT_RAW:
		format = qcow2.DriverRaw

	default:
		format = qcow2.DriverQCow2
	}

	ClusterSize := 4096
	if req.ClusterSize == proto.ClusterSize_CLUSTER_SIZE_64K {
		ClusterSize = 65536
	}

	LazyRefcounts := true
	if req.Lazyrefcounts == proto.LazyRefcounts_LAZY_REFCOUNTS_FALSE {
		LazyRefcounts = false
	}

	opts := &qcow2.Opts{
		Filename:      req.Filename,
		Size:          req.Size * 107374,
		Fmt:           format,
		ClusterSize:   ClusterSize,
		Preallocation: qcow2.PREALLOC_MODE_OFF,
		Encryption:    false,
		LazyRefcounts: LazyRefcounts,
	}

	_, err = qcow2.Create(opts)
	if err == nil {
		return &proto.CreateDiskResponse{Result: true}, nil
	}
	return &proto.CreateDiskResponse{Result: false}, status.Error(codes.Unimplemented, err.Error())
}

func (h *DiskOperationsServer) DeleteDisk(ctx context.Context, req *proto.DeleteDiskRequest) (*proto.DeleteDiskResponse, error) {

	_, err := os.Stat(req.Filename)
	if err == nil {
		err = os.Remove(req.Filename)
		if err == nil {
			return &proto.DeleteDiskResponse{Result: true}, nil
		} else {
			return &proto.DeleteDiskResponse{Result: false}, status.Error(codes.Internal, err.Error())
		}

	}
	return &proto.DeleteDiskResponse{Result: true}, nil
}

func (h *DiskOperationsServer) DerivateDisk(ctx context.Context, req *proto.DerivateDiskRequest) (*proto.DerivateDiskResponse, error) {

	// Destination already exists
	_, err := os.Stat(req.Filename)
	if os.IsExist(err) {
		return &proto.DerivateDiskResponse{Result: true}, nil
	}

	// Backing file exists
	_, err = os.Stat(req.Backingfile)
	if os.IsNotExist(err) {
		return &proto.DerivateDiskResponse{Result: false}, status.Error(codes.NotFound, err.Error())
	}

	// If path not exists, create
	dir, _ := path.Split(req.Filename)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		os.Mkdir(dir, os.ModePerm)
	}

	args := []string{"create", "-f", "qcow2"}
	args = append(args, "-o")
	args = append(args, fmt.Sprintf("backing_file=%s", req.Backingfile))
	args = append(args, req.Filename)
	//args = append(args, strconv.FormatUint(i.Size, 10))

	cmd := exec.Command("qemu-img", args...)

	_, err = cmd.CombinedOutput()
	if err != nil {
		//return fmt.Errorf("'qemu-img create' output: %s", oneLine(out))
		return &proto.DerivateDiskResponse{Result: false}, status.Error(codes.Internal, err.Error())
	}

	return &proto.DerivateDiskResponse{Result: true}, nil
}

func (h *DiskOperationsServer) MoveDisk(ctx context.Context, req *proto.MoveDiskRequest) (*proto.MoveDiskResponse, error) {

	_, err := os.Stat(req.Destination)
	if os.IsExist(err) {
		return &proto.MoveDiskResponse{Result: false}, status.Error(codes.Unimplemented, err.Error())
	}

	_, err = os.Stat(req.Source)
	if os.IsNotExist(err) {
		return &proto.MoveDiskResponse{Result: false}, status.Error(codes.Unimplemented, err.Error())
	}

	dir, _ := path.Split(req.Destination)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		os.Mkdir(dir, os.ModePerm)
	}

	err = os.Rename(req.Source, req.Destination)

	if err == nil {
		return &proto.MoveDiskResponse{Result: true}, nil
	}
	return &proto.MoveDiskResponse{Result: false}, status.Error(codes.Unimplemented, err.Error())
}
