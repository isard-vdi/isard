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

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/check/check"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	"gitlab.com/isard/isardvdi/pkg/log"
	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
)

var ErrHypersNum = errors.New("hypervisors number missmatch")

const (
	StateOk   = "OK"
	StateWarn = "WARN"
	StateFail = "FAIL"
)

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
		go doCheck(ctx, &wg, m.Config.CheckAddr, instance)
	}

	wg.Wait()

	msg := time.Now().Format(time.RFC3339) + "\n"
	var failed bool
	for _, instance := range m.Instances {
		iMsg, iFail := handleInstance(log, instance)
		if iFail {
			failed = true
		}

		msg += iMsg
	}

	if failed {
		if err := sendTelegramMsg(m.Config, msg); err != nil {
			log.Fatal().Err(err).Msg("send telegram message")
		}
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

func doCheck(ctx context.Context, wg *sync.WaitGroup, checkAddr string, instance *MonitorInstance) {
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

func handleInstance(log *zerolog.Logger, i *MonitorInstance) (string, bool) {
	state := StateOk
	extra := ""

	if i.RspErr != nil {
		if errors.Is(i.RspErr, ErrHypersNum) {
			log.Warn().Str("host", i.Host).Int("expected_hypers", i.HypersNum).Int32("actual_hypers", i.Rsp.HypervisorNum).Str("isardvdi_version", i.Rsp.IsardvdiVersion).Msg("check finished")
			state = StateWarn

		} else {
			log.Error().Str("host", i.Host).Err(i.RspErr).Msg("check failed")
			state = StateFail

			var err error
			s, ok := status.FromError(i.RspErr)
			if !ok {
				err = i.RspErr
			} else {
				err = errors.New(s.Message())
			}

			// OutOfAttempts is a viewer error
			if errors.Is(err, check.ErrViewerOutOfAttempts) {
				// Check for SPICE
				if errors.Is(err, check.ErrViewerSpice) {
					err = check.ErrViewerSpice

					// Check for RDP GW
				} else if errors.Is(err, check.ErrViewerRDPGW) {
					err = check.ErrViewerRDPGW

					// Check for RDP VPN
				} else if errors.Is(err, check.ErrViewerRDPVPN) {
					err = check.ErrViewerRDPVPN

				} else {
					err = fmt.Errorf("unknown viewer error: %w", err)
				}
			}

			extra += fmt.Sprintf("\n%s\n", err)
		}

	} else {
		log.Info().Str("host", i.Host).Str("isardvdi_version", i.Rsp.IsardvdiVersion).Msg("check finished")
	}

	return fmt.Sprintf("%s (%d/%d) %s - %s%s", state, i.Rsp.GetHypervisorNum(), i.HypersNum, i.Host, i.Rsp.GetIsardvdiVersion(), extra), state != StateOk
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
