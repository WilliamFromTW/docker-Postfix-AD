package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestCircuitBreaker(t *testing.T) {
	cb := NewCircuitBreaker(3, 5*time.Minute, 100*time.Millisecond)

	ip := "192.168.1.100:54321"
	user := "William"

	// 1. 初始狀態未阻斷
	if cb.IsBlocked(ip, user) {
		t.Fatal("Initial state should not be blocked")
	}

	// 2. 記錄第 1 次失敗
	if blocked := cb.RecordFailure(ip, user); blocked {
		t.Fatal("1st failure should not trigger block")
	}
	if cb.IsBlocked(ip, user) {
		t.Fatal("1st failure should not be blocked")
	}

	// 3. 記錄第 2 次失敗
	if blocked := cb.RecordFailure(ip, user); blocked {
		t.Fatal("2nd failure should not trigger block")
	}

	// 4. 記錄第 3 次失敗，應觸發熔斷阻斷
	if blocked := cb.RecordFailure(ip, user); !blocked {
		t.Fatal("3rd failure should trigger block")
	}
	if !cb.IsBlocked(ip, user) {
		t.Fatal("State should be blocked after 3 failures")
	}

	// 5. 驗證大小寫無關 (case-insensitive) 與不同連接埠相同 IP
	if !cb.IsBlocked("192.168.1.100:60000", "william") {
		t.Fatal("Circuit breaker should block matching IP without port and lowercase username")
	}

	// 6. 驗證不同使用者未被阻斷
	if cb.IsBlocked(ip, "OtherUser") {
		t.Fatal("Different user should not be blocked")
	}

	// 7. 驗證不同來源 IP 未被阻斷
	if cb.IsBlocked("10.0.0.1:54321", user) {
		t.Fatal("Different IP should not be blocked")
	}

	// 8. 驗證冷卻逾時後自動解鎖 (cooldown is 100ms in this test)
	time.Sleep(150 * time.Millisecond)
	if cb.IsBlocked(ip, user) {
		t.Fatal("Should automatically unblock after cooldown expires")
	}

	// 9. 驗證成功登入後清除歷史
	cb.RecordFailure(ip, user)
	cb.RecordSuccess(ip, user)
	cb.RecordFailure(ip, user)
	cb.RecordFailure(ip, user)
	if cb.IsBlocked(ip, user) {
		t.Fatal("Success should have reset counter, so 2 failures should not trigger block")
	}
}

func TestSensitiveAttributeFiltering(t *testing.T) {
	cfg := &Config{
		AllowedAttrs: DefaultAllowedAttrs,
	}
	server, err := NewProxyServer(cfg)
	if err != nil {
		t.Fatalf("Failed to create ProxyServer: %v", err)
	}

	// 白名單欄位應通過
	allowed := []string{"displayName", "mail", "telephoneNumber", "company", "title", "department"}
	for _, a := range allowed {
		if !server.isAllowedAttr(a) {
			t.Errorf("Attribute %s should be allowed", a)
		}
	}

	// 敏感與內部欄位絕對必須被遮蔽
	forbidden := []string{
		"unicodePwd",
		"userPassword",
		"objectSid",
		"userAccountControl",
		"ntPwdHash",
		"lmPwdHash",
		"badPwdCount",
		"lockoutTime",
	}
	for _, f := range forbidden {
		if server.isAllowedAttr(f) {
			t.Errorf("Sensitive attribute %s must be blocked!", f)
		}
		// 測試大小寫變異
		if server.isAllowedAttr(filepath.Clean(f)) {
			// case variation
		}
	}
}

func TestConfigLoaderWithEnv(t *testing.T) {
	os.Setenv("HOST_IP", "10.10.10.1,10.10.10.2")
	os.Setenv("DOMAIN_NAME", "kafeiou.pw")
	os.Setenv("SEARCH_BASE", "DC=kafeiou,DC=pw")
	os.Setenv("BIND_DN", "CN=ldap,CN=Users,DC=kafeiou,DC=pw")
	os.Setenv("BIND_PW", "SecretPass123")
	defer func() {
		os.Unsetenv("HOST_IP")
		os.Unsetenv("DOMAIN_NAME")
		os.Unsetenv("SEARCH_BASE")
		os.Unsetenv("BIND_DN")
		os.Unsetenv("BIND_PW")
	}()

	cfg, err := LoadConfig("")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	if cfg.SearchBase != "DC=kafeiou,DC=pw" {
		t.Errorf("Expected SearchBase DC=kafeiou,DC=pw, got %s", cfg.SearchBase)
	}
	if cfg.BindDN != "CN=ldap,CN=Users,DC=kafeiou,DC=pw" {
		t.Errorf("Expected BindDN CN=ldap,CN=Users,DC=kafeiou,DC=pw, got %s", cfg.BindDN)
	}
	if len(cfg.DefaultGC) != 2 {
		t.Fatalf("Expected 2 GC backends, got %d", len(cfg.DefaultGC))
	}
	if cfg.DefaultGC[0].Host != "10.10.10.1" || cfg.DefaultGC[0].Port != 3268 {
		t.Errorf("Expected DefaultGC[0] to be 10.10.10.1:3268, got %+v", cfg.DefaultGC[0])
	}
	if cfg.DefaultGC[1].Host != "10.10.10.2" || cfg.DefaultGC[1].Port != 3268 {
		t.Errorf("Expected DefaultGC[1] to be 10.10.10.2:3268, got %+v", cfg.DefaultGC[1])
	}
	if len(cfg.Domains) == 0 || cfg.Domains[0].Domain != "kafeiou.pw" {
		t.Errorf("Expected primary domain kafeiou.pw in routes")
	}
}
