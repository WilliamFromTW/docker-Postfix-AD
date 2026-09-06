package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// BackendDC 定義單一 Active Directory 後端主機
type BackendDC struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
}

// DomainRoute 定義特定網域之查詢基底與後端 DC 清單
type DomainRoute struct {
	Domain     string      `yaml:"domain"`
	SearchBase string      `yaml:"search_base"`
	Backends   []BackendDC `yaml:"backends"`
}

// Config 包含 LDAPS GAL Proxy 的完整運行參數
type Config struct {
	ListenAddr   string        `yaml:"listen_addr"`
	CertFile     string        `yaml:"cert_file"`
	KeyFile      string        `yaml:"key_file"`
	LogFile      string        `yaml:"log_file"`
	DefaultGC    []BackendDC   `yaml:"default_gc"`
	Domains      []DomainRoute `yaml:"domains"`
	AllowedAttrs []string      `yaml:"allowed_attrs"`
	MaxFailures  int           `yaml:"max_failures"`
	CooldownMin  int           `yaml:"cooldown_min"`
	CooldownSec  int           `yaml:"cooldown_sec"`
	WindowMin    int           `yaml:"window_min"`
	SearchBase   string        `yaml:"search_base"`
	BindDN       string        `yaml:"bind_dn"`
	BindPW       string        `yaml:"bind_pw"`
}

// 預設通訊錄白名單欄位
var DefaultAllowedAttrs = []string{
	"displayName",
	"mail",
	"telephoneNumber",
	"mobile",
	"company",
	"department",
	"title",
	"physicalDeliveryOfficeName",
	"sAMAccountName",
	"userPrincipalName",
	"cn",
	"givenName",
	"sn",
	"streetAddress",
	"postalCode",
	"c",
	"l",
	"st",
	"objectClass",
}

// LoadConfig 載入配置檔案，若檔案不存在則從環境變數自動推導
func LoadConfig(configPath string) (*Config, error) {
	cfg := &Config{
		ListenAddr:   ":3269",
		LogFile:      "/var/log/ldaps-gal-proxy.log",
		MaxFailures:  5,
		CooldownSec:  30,
		CooldownMin:  0,
		WindowMin:    5,
		AllowedAttrs: DefaultAllowedAttrs,
	}

	// 1. 若配置檔存在則優先讀取
	if configPath != "" {
		if data, err := os.ReadFile(configPath); err == nil {
			if err := yaml.Unmarshal(data, cfg); err != nil {
				return nil, fmt.Errorf("failed to parse config %s: %w", configPath, err)
			}
		}
	}

	// 2. 從環境變數自動推導未指定之項目
	hostIP := os.Getenv("HOST_IP")
	if hostIP == "" {
		hostIP = "127.0.0.1"
	}

	searchBase := os.Getenv("SEARCH_BASE")
	if searchBase == "" {
		searchBase = "DC=example,DC=com"
	}
	if cfg.SearchBase == "" {
		cfg.SearchBase = searchBase
	}

	domainName := os.Getenv("DOMAIN_NAME")
	if domainName == "" {
		domainName = "example.com"
	}

	if cfg.BindDN == "" {
		cfg.BindDN = os.Getenv("BIND_DN")
	}
	if cfg.BindPW == "" {
		cfg.BindPW = os.Getenv("BIND_PW")
	}

	// 若未指定 DefaultGC，從 HOST_IP 建構
	if len(cfg.DefaultGC) == 0 {
		hosts := strings.Split(hostIP, ",")
		for _, h := range hosts {
			h = strings.TrimSpace(h)
			if h != "" {
				cfg.DefaultGC = append(cfg.DefaultGC, BackendDC{
					Host: h,
					Port: 3268, // Global Catalog default port
				})
			}
		}
	}

	// 若未指定 Domains，自動由 DOMAIN_NAME 與 LOCAL_ONLY_DOMAINS 建立
	if len(cfg.Domains) == 0 {
		cfg.Domains = append(cfg.Domains, DomainRoute{
			Domain:     domainName,
			SearchBase: cfg.SearchBase,
			Backends:   cfg.DefaultGC,
		})

		for _, envKey := range []string{"LOCAL_ONLY_DOMAINS", "LOCAL_ONLY2_DOMAINS"} {
			if val := os.Getenv(envKey); val != "" {
				for _, subDomain := range strings.Fields(val) {
					subDomain = strings.TrimSpace(subDomain)
					if subDomain != "" {
						cfg.Domains = append(cfg.Domains, DomainRoute{
							Domain:     subDomain,
							SearchBase: cfg.SearchBase,
							Backends:   cfg.DefaultGC,
						})
					}
				}
			}
		}
	}

	// 3. 憑證路徑探測
	hostName := os.Getenv("HOST_NAME")
	if hostName == "" {
		hostName = domainName
	}

	if cfg.CertFile == "" || cfg.KeyFile == "" {
		leCert := filepath.Join("/etc/letsencrypt/live", hostName, "fullchain.pem")
		leKey := filepath.Join("/etc/letsencrypt/live", hostName, "privkey.pem")

		if fileExists(leCert) && fileExists(leKey) {
			cfg.CertFile = leCert
			cfg.KeyFile = leKey
		} else {
			// 回退自簽憑證或暫存憑證
			fallbackCert := "/etc/dovecot/cert.pem"
			fallbackKey := "/etc/dovecot/key.pem"
			if fileExists(fallbackCert) && fileExists(fallbackKey) {
				cfg.CertFile = fallbackCert
				cfg.KeyFile = fallbackKey
			} else {
				// 自動產生記憶體臨時憑證供測試或防呆
				tempCert, tempKey, err := generateSelfSignedCert(hostName)
				if err == nil {
					cfg.CertFile = tempCert
					cfg.KeyFile = tempKey
				}
			}
		}
	}

	return cfg, nil
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir()
}

// generateSelfSignedCert 在找不到任何實體憑證時動態建立臨時 TLS 憑證
func generateSelfSignedCert(hostName string) (string, string, error) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return "", "", err
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(time.Now().UnixNano()),
		Subject: pkix.Name{
			CommonName:   hostName,
			Organization: []string{"Postfix-AD Temporary GAL Proxy"},
		},
		NotBefore:             time.Now().Add(-1 * time.Hour),
		NotAfter:              time.Now().Add(365 * 24 * time.Hour),
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		DNSNames:              []string{hostName, "localhost"},
		IPAddresses:           []net.IP{net.ParseIP("127.0.0.1")},
	}

	derBytes, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		return "", "", err
	}

	tempDir := os.TempDir()
	certFile := filepath.Join(tempDir, "gal_proxy_temp_cert.pem")
	keyFile := filepath.Join(tempDir, "gal_proxy_temp_key.pem")

	certOut, err := os.Create(certFile)
	if err != nil {
		return "", "", err
	}
	defer certOut.Close()
	if err := pem.Encode(certOut, &pem.Block{Type: "CERTIFICATE", Bytes: derBytes}); err != nil {
		return "", "", err
	}

	keyOut, err := os.OpenFile(keyFile, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return "", "", err
	}
	defer keyOut.Close()
	privBytes, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		return "", "", err
	}
	if err := pem.Encode(keyOut, &pem.Block{Type: "PRIVATE KEY", Bytes: privBytes}); err != nil {
		return "", "", err
	}

	return certFile, keyFile, nil
}
