package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	configPath := flag.String("config", "", "Path to YAML configuration file")
	flag.Parse()

	// 若未傳入 -config，檢查預設路徑
	cfgPath := *configPath
	if cfgPath == "" {
		candidates := []string{
			"/etc/ldaps-proxy/config.yaml",
			"/etc/ldaps-gal-proxy/config.yaml",
			"config.yaml",
		}
		for _, c := range candidates {
			if fileExists(c) {
				cfgPath = c
				break
			}
		}
	}

	cfg, err := LoadConfig(cfgPath)
	if err != nil {
		log.Fatalf("Failed to initialize configuration: %v", err)
	}

	proxy, err := NewProxyServer(cfg)
	if err != nil {
		log.Fatalf("Failed to create GAL proxy: %v", err)
	}

	// 捕獲系統中斷訊號以實現優雅停止
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		log.Printf("Received signal %v, shutting down...", sig)
		proxy.Stop()
		os.Exit(0)
	}()

	log.Printf("Starting LDAPS GAL Proxy on %s...", cfg.ListenAddr)
	if err := proxy.Start(); err != nil {
		log.Fatalf("LDAPS GAL Proxy runtime error: %v", err)
	}
}
