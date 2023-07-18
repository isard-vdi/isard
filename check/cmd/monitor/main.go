package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	"gitlab.com/isard/isardvdi/pkg/log"
	"google.golang.org/grpc"
)

var ErrHypersNum = errors.New("hypervisors number missmatch")

func main() {
	log := log.New("monitor", "info")
	if len(os.Args) != 2 {
		log.Fatal().Msg("incorrect script call (first arg should be the path to the monitor file)")
	}

	// Read the monitor file to know what hosts should be checked
	b, err := os.ReadFile(os.Args[1])
	if err != nil {
		log.Fatal().Err(err).Msg("read monitor config file")
	}

	m := Monitor{}
	if err := json.Unmarshal(b, &m); err != nil {
		log.Fatal().Err(err).Msg("unmarshal monitor config file")
	}

	ctx := context.Background()

	// Check all the hosts in parallel
	var wg sync.WaitGroup
	for _, i := range m.Instances {
		wg.Add(1)
		instance := i
		go check(ctx, &wg, m.Config.CheckAddr, instance)
	}

	wg.Wait()

	msg := time.Now().Format(time.RFC3339) + "\n"
	var failed error
	for _, instance := range m.Instances {
		if instance.RspErr != nil {
			failed = instance.RspErr

			if errors.Is(instance.RspErr, ErrHypersNum) {
				log.Warn().Str("host", instance.Host).Int("expected_hypers", instance.HypersNum).Int32("actual_hypers", instance.Rsp.HypervisorNum).Str("isardvdi_version", instance.Rsp.IsardvdiVersion).Msg("check finished")
				msg += fmt.Sprintf("WARN (%d/%d) %s - %s\n", instance.Rsp.HypervisorNum, instance.HypersNum, instance.Host, instance.Rsp.IsardvdiVersion)
			} else {
				log.Error().Str("host", instance.Host).Err(instance.RspErr).Msg("check failed")
				msg += fmt.Sprintf("FAIL (?/?) %s - ???\n", instance.Host)
				err = instance.RspErr
			}
		} else {
			log.Info().Str("host", instance.Host).Str("isardvdi_version", instance.Rsp.IsardvdiVersion).Msg("check finished")
			msg += fmt.Sprintf("OK   (%d/%d) %s - %s\n", instance.Rsp.HypervisorNum, instance.HypersNum, instance.Host, instance.Rsp.IsardvdiVersion)
		}
	}

	if failed != nil {
		if err := sendTelegramMsg(m.Config, msg); err != nil {
			log.Fatal().Err(err).Msg("send telegram message")
		}

		msg += fmt.Sprintf("\n\n  --- FAILED --- \n\n%v", err)
	}

	if err := os.WriteFile(filepath.Join(os.TempDir(), "monitor.log"), []byte(msg), 0644); err != nil {
		log.Fatal().Err(err).Msg("write log file")
	}
}

type Monitor struct {
	Config    MonitorConfig      `json:"config"`
	Instances []*MonitorInstance `json:"instances"`
}

type MonitorConfig struct {
	CheckAddr string `json:"check_addr"`
	ChatID    string `json:"chat_id"`
	BotToken  string `json:"bot_token"`
}

type MonitorInstance struct {
	Host            string                         `json:"host"`
	Category        string                         `json:"category"`
	Username        string                         `json:"username"`
	Password        string                         `json:"password"`
	TemplateID      string                         `json:"template_id"`
	HypersNum       int                            `json:"hypers_num"`
	FailMaintenance bool                           `json:"fail_maintenance"`
	FailSelfSigned  bool                           `json:"fail_self_signed"`
	Rsp             *checkv1.CheckIsardVDIResponse `json:"-"`
	RspErr          error                          `json:"-"`
}

func check(ctx context.Context, wg *sync.WaitGroup, checkAddr string, instance *MonitorInstance) {
	defer wg.Done()

	opts := []grpc.DialOption{grpc.WithInsecure()}
	conn, err := grpc.DialContext(ctx, checkAddr, opts...)
	if err != nil {
		panic(err)
	}
	defer conn.Close()

	cli := checkv1.NewCheckServiceClient(conn)

	rsp, err := cli.CheckIsardVDI(ctx, &checkv1.CheckIsardVDIRequest{
		Host: instance.Host,
		Auth: &checkv1.Auth{
			Method: &checkv1.Auth_Form{
				Form: &checkv1.AuthForm{
					Category: instance.Category,
					Username: instance.Username,
					Password: instance.Password,
				},
			},
		},
		TemplateId:          instance.TemplateID,
		FailMaintenanceMode: instance.FailMaintenance,
		FailSelfSigned:      instance.FailSelfSigned,
	})
	if err != nil {
		instance.RspErr = err
	} else {
		if instance.HypersNum != 0 && int(rsp.HypervisorNum) != instance.HypersNum {
			instance.RspErr = ErrHypersNum
		}
	}

	instance.Rsp = rsp
}

func sendTelegramMsg(cfg MonitorConfig, msg string) error {
	b, err := json.Marshal(struct {
		ChatID    string `json:"chat_id"`
		ParseMode string `json:"parse_mode"`
		Text      string `json:"text"`
	}{
		ChatID:    cfg.ChatID,
		ParseMode: "markdown",
		Text:      "```\n" + msg + "```\n",
	})
	if err != nil {
		return err
	}
	body := bytes.NewBuffer(b)

	if _, err := http.Post(fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", cfg.BotToken), "application/json", body); err != nil {
		return err
	}

	return nil
}
