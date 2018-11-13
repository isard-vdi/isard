package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/isard-vdi/isard-ipxe/pkg/handlers"
)

type logWriter struct {
	File *os.File
}

func (w *logWriter) Write(b []byte) (int, error) {
	fmt.Print(string(b[:]))

	return w.File.Write(b)
}

func configureLogging() {
	f, err := os.OpenFile("isard-ipxe.log", os.O_RDWR|os.O_CREATE|os.O_APPEND, 0644)
	if err != nil {
		log.Fatalf("error opening log file: %v", err)
	}
	defer f.Close()

	w := &logWriter{
		File: f,
	}

	log.SetOutput(w)
}

func generateMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/", handlers.LoginHandler)
	mux.HandleFunc("/auth", handlers.AuthHandler)
	mux.HandleFunc("/list", handlers.VMListHandler)
	mux.HandleFunc("/start", handlers.StartHandler)

	return mux
}

func main() {
	// Server setup
	configureLogging()
	mux := generateMux()

	// Start the server
	log.Println("Starting to listen at port :8080")
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatalf("error listening the server: %v", err)
	}
}
