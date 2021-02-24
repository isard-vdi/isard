package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/backend/cfg"
	"gitlab.com/isard/isardvdi/backend/transport/http"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
	"gitlab.com/isard/isardvdi/pkg/proto/controller"

	"google.golang.org/grpc"
)

func main() {
	cfg := cfg.New()

	log := log.New("backend", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	db, err := db.New(fmt.Sprintf("%s:%d", cfg.DB.Host, cfg.DB.Port), cfg.DB.Usr, cfg.DB.Pwd, cfg.DB.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	authConn, err := grpc.Dial(cfg.ClientsAddr.Auth, grpc.WithInsecure())
	if err != nil {
		log.Fatal().Err(err).Msg("dial auth")
	}
	auth := auth.NewAuthClient(authConn)

	controllerConn, err := grpc.Dial(cfg.ClientsAddr.Controller, grpc.WithInsecure())
	if err != nil {
		log.Fatal().Err(err).Msg("dial controller")
	}
	controller := controller.NewControllerClient(controllerConn)
	// TODO: DEfer!!!

	fmt.Println(cfg.ClientsAddr.Controller)

	http := &http.BackendServer{
		Addr: fmt.Sprintf("%s:%d", cfg.GraphQL.Host, cfg.GraphQL.Port),

		DB:             db,
		AuthConn:       authConn,
		Auth:           auth,
		ControllerConn: controllerConn,
		Controller:     controller,

		Log: log,
		WG:  &wg,
	}
	go http.Serve(ctx)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
