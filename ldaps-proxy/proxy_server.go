package main

import (
	"crypto/tls"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/go-ldap/ldap/v3"
	"github.com/lor00x/goldap/message"
	"github.com/vjeantet/ldapserver"
)

var sensitiveAttrs = map[string]bool{
	"unicodepwd":         true,
	"userpassword":       true,
	"objectsid":          true,
	"useraccountcontrol": true,
	"ntpwdhash":          true,
	"lmpwdhash":          true,
	"dbcspwd":            true,
	"badpasswordtime":    true,
	"badpwdcount":        true,
	"pwdlastset":         true,
	"lockouttime":        true,
}

// ClientSession 儲存特定 TCP 連線的工作階段驗證身分
type ClientSession struct {
	Username      string
	UserDN        string
	UserUPN       string
	ClientIP      string
	Password      string
	Authenticated bool
}

// ProxyServer 是 LDAPS GAL Proxy 的核心服務結構
type ProxyServer struct {
	cfg       *Config
	cb        *CircuitBreaker
	server    *ldapserver.Server
	logFile   *os.File
	logMu     sync.Mutex
	isRunning bool
	sessions  map[string]*ClientSession
	sessMu    sync.RWMutex
}

// NewProxyServer 建立 LDAPS GAL Proxy 伺服器
func NewProxyServer(cfg *Config) (*ProxyServer, error) {
	cooldownDuration := 30 * time.Second
	if cfg.CooldownSec > 0 {
		cooldownDuration = time.Duration(cfg.CooldownSec) * time.Second
	} else if cfg.CooldownMin > 0 {
		cooldownDuration = time.Duration(cfg.CooldownMin) * time.Minute
	}

	cb := NewCircuitBreaker(
		cfg.MaxFailures,
		time.Duration(cfg.WindowMin)*time.Minute,
		cooldownDuration,
	)

	ps := &ProxyServer{
		cfg:      cfg,
		cb:       cb,
		sessions: make(map[string]*ClientSession),
	}

	// 初始化日誌輸出
	if cfg.LogFile != "" {
		_ = os.MkdirAll(filepath.Dir(cfg.LogFile), 0755)
		f, err := os.OpenFile(cfg.LogFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if err == nil {
			ps.logFile = f
		}
	}

	return ps, nil
}

func (s *ProxyServer) setSession(clientAddr string, sess *ClientSession) {
	s.sessMu.Lock()
	defer s.sessMu.Unlock()
	s.sessions[clientAddr] = sess
}

func (s *ProxyServer) getSession(clientAddr string) *ClientSession {
	s.sessMu.RLock()
	defer s.sessMu.RUnlock()
	return s.sessions[clientAddr]
}

func (s *ProxyServer) logAudit(format string, args ...interface{}) {
	s.logMu.Lock()
	defer s.logMu.Unlock()

	msg := fmt.Sprintf(format, args...)
	line := fmt.Sprintf("[%s] %s\n", time.Now().Format("2006-01-02 15:04:05"), msg)
	fmt.Print(line)
	if s.logFile != nil {
		_, _ = s.logFile.WriteString(line)
	}
}

// isAllowedAttr 依據白名單過濾屬性並絕對遮蔽敏感欄位
func (s *ProxyServer) isAllowedAttr(name string) bool {
	lower := strings.ToLower(strings.TrimSpace(name))
	if sensitiveAttrs[lower] {
		return false
	}
	if len(s.cfg.AllowedAttrs) == 0 {
		return true
	}
	for _, allowed := range s.cfg.AllowedAttrs {
		if strings.EqualFold(allowed, lower) {
			return true
		}
	}
	return false
}

// getBackendGC 嘗試連線至可用的後端 Global Catalog (Port 3268) 主機 (支援 StartTLS 與 LDAPS)
func (s *ProxyServer) getBackendGC() (*ldap.Conn, error) {
	var lastErr error
	tlsConfig := &tls.Config{InsecureSkipVerify: true}

	for _, backend := range s.cfg.DefaultGC {
		addr := fmt.Sprintf("%s:%d", backend.Host, backend.Port)

		// 1. 若配置直接為 LDAPS 連接埠 (3269 或 636)，以 TLS 直連
		if backend.Port == 3269 || backend.Port == 636 {
			conn, err := ldap.DialURL(fmt.Sprintf("ldaps://%s", addr),
				ldap.DialWithDialer(&net.Dialer{Timeout: 5 * time.Second}),
				ldap.DialWithTLSConfig(tlsConfig),
			)
			if err == nil {
				return conn, nil
			}
			lastErr = err
			continue
		}

		// 2. 對於 Port 3268 / 389：先建立 TCP 連線，並自動升級 StartTLS 傳輸加密 (滿足 AD "Transport encryption required" 要求)
		conn, err := ldap.DialURL(fmt.Sprintf("ldap://%s", addr),
			ldap.DialWithDialer(&net.Dialer{Timeout: 5 * time.Second}),
		)
		if err == nil {
			if tlsErr := conn.StartTLS(tlsConfig); tlsErr == nil {
				return conn, nil
			}

			// 若 StartTLS 協商失敗，嘗試備援探測 AD 是否開啟 3269 (LDAPS GC)
			ldapsAddr := fmt.Sprintf("%s:3269", backend.Host)
			ldapsConn, ldapsErr := ldap.DialURL(fmt.Sprintf("ldaps://%s", ldapsAddr),
				ldap.DialWithDialer(&net.Dialer{Timeout: 3 * time.Second}),
				ldap.DialWithTLSConfig(tlsConfig),
			)
			if ldapsErr == nil {
				conn.Close()
				return ldapsConn, nil
			}

			// 若無法升級 TLS，返回原明文連線以相容未開啟 TLS 的純內網測試環境
			return conn, nil
		}
		lastErr = err
	}
	if lastErr == nil {
		return nil, fmt.Errorf("no backend GC servers configured")
	}
	return nil, fmt.Errorf("all backend GC servers unreachable: %w", lastErr)
}

// resolveUserIdentity 在 Global Catalog (3268) 中以純帳號查詢真實 DN 與 UPN
func (s *ProxyServer) resolveUserIdentity(username string) (string, string, error) {
	gc, err := s.getBackendGC()
	if err != nil {
		return "", "", err
	}
	defer gc.Close()

	// 若配置了管理員 BindDN 則先行 Bind，否則嘗試匿名搜尋
	if s.cfg.BindDN != "" {
		if err := gc.Bind(s.cfg.BindDN, s.cfg.BindPW); err != nil {
			return "", "", fmt.Errorf("service bind to GC failed: %w", err)
		}
	}

	escapedUser := ldap.EscapeFilter(username)
	searchReq := ldap.NewSearchRequest(
		s.cfg.SearchBase,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases,
		1,
		10,
		false,
		fmt.Sprintf("(&(objectCategory=person)(objectClass=user)(sAMAccountName=%s))", escapedUser),
		[]string{"distinguishedName", "userPrincipalName", "sAMAccountName"},
		nil,
	)

	sr, err := gc.Search(searchReq)
	if err != nil {
		return "", "", fmt.Errorf("GC user search failed: %w", err)
	}

	if len(sr.Entries) == 0 {
		return "", "", fmt.Errorf("user %s not found in GC", username)
	}

	entry := sr.Entries[0]
	dn := entry.DN
	upn := entry.GetAttributeValue("userPrincipalName")
	if upn == "" {
		// 若無 UPN，推導 username@DOMAIN_NAME
		domain := ""
		if len(s.cfg.Domains) > 0 {
			domain = s.cfg.Domains[0].Domain
		}
		if domain != "" {
			upn = fmt.Sprintf("%s@%s", username, domain)
		}
	}

	return dn, upn, nil
}

// HandleBind 處理客戶端身分驗證（二階段驗證 + 防爆破熔斷）
func (s *ProxyServer) HandleBind(w ldapserver.ResponseWriter, m *ldapserver.Message) {
	r := m.GetBindRequest()
	rawUser := string(r.Name())
	password := string(r.AuthenticationSimple())

	clientAddr := ""
	if m.Client != nil && m.Client.Addr() != nil {
		clientAddr = m.Client.Addr().String()
	}

	// 1. 匿名 Bind 檢查 (常用於初次探測)
	if rawUser == "" && password == "" {
		s.logAudit("[AUTH_ANONYMOUS] client=%s", clientAddr)
		s.setSession(clientAddr, &ClientSession{
			ClientIP:      clientAddr,
			Authenticated: false,
		})
		w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultSuccess))
		return
	}

	// 2. 檢查短時間頻率防抖 (Debounce 1s)：同帳號請求間隔小於 1 秒回傳 Busy，避免瞬時並發刷爆
	if s.cb.CheckRateLimit(clientAddr, rawUser, 1*time.Second) {
		s.logAudit("[RATE_LIMIT_BUSY] client=%s user=%q request too frequent (<1s), replying busy", clientAddr, rawUser)
		w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultBusy))
		return
	}

	// 3. 檢查防爆破熔斷器 (Anti-Lockout)：處於冷卻期時回傳 Busy 打破 Thunderbird 無限彈窗死循環
	if s.cb.IsBlocked(clientAddr, rawUser) {
		s.logAudit("[CIRCUIT_BREAK] client=%s user=%q blocked for cooldown window (protecting AD from lockout), replying busy", clientAddr, rawUser)
		w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultBusy))
		return
	}

	// 3. 二階段驗證：若為純帳號 (無 @ 且無 =)，自 GC (3268) 解析出真實 UPN / DN
	var targetBindUser string
	var resolvedDN, resolvedUPN string

	if !strings.Contains(rawUser, "@") && !strings.Contains(rawUser, "=") {
		dn, upn, err := s.resolveUserIdentity(rawUser)
		if err != nil {
			s.logAudit("[AUTH_FAIL_LOOKUP] client=%s user=%q err=%v", clientAddr, rawUser, err)
			// 僅在明確「使用者不存在於 GC」時計入失敗熔斷次數；
			// 若為後端服務連線失敗或 AD 傳輸加密問題，屬於後端系統異常，回傳 OperationsError，不鎖定使用者帳號
			if strings.Contains(err.Error(), "not found in GC") {
				blocked := s.cb.RecordFailure(clientAddr, rawUser)
				if blocked {
					s.logAudit("[CIRCUIT_TRIGGERED] client=%s user=%q triggered cooldown for %d minutes", clientAddr, rawUser, s.cfg.CooldownMin)
				}
				w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultInvalidCredentials))
			} else {
				w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultOperationsError))
			}
			return
		}
		resolvedDN = dn
		resolvedUPN = upn
		if upn != "" {
			targetBindUser = upn
		} else {
			targetBindUser = dn
		}
	} else {
		targetBindUser = rawUser
		resolvedUPN = rawUser
	}

	// 4. 向後端 GC / DC 進行密碼驗證 (Bind)
	backendConn, err := s.getBackendGC()
	if err != nil {
		s.logAudit("[AUTH_ERROR_BACKEND] client=%s user=%q err=%v", clientAddr, rawUser, err)
		w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultOperationsError))
		return
	}
	defer backendConn.Close()

	if err := backendConn.Bind(targetBindUser, password); err != nil {
		s.logAudit("[AUTH_FAIL] client=%s user=%q bind_target=%q err=%v", clientAddr, rawUser, targetBindUser, err)
		blocked := s.cb.RecordFailure(clientAddr, rawUser)
		if blocked {
			s.logAudit("[CIRCUIT_TRIGGERED] client=%s user=%q triggered cooldown for 30s", clientAddr, rawUser)
			w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultBusy))
			return
		}
		w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultInvalidCredentials))
		return
	}

	// 5. 驗證成功：清除失敗計數並儲存工作階段狀態
	s.cb.RecordSuccess(clientAddr, rawUser)
	s.logAudit("[AUTH_SUCCESS] client=%s user=%q resolved_upn=%q", clientAddr, rawUser, resolvedUPN)

	s.setSession(clientAddr, &ClientSession{
		Username:      rawUser,
		UserDN:        resolvedDN,
		UserUPN:       resolvedUPN,
		ClientIP:      clientAddr,
		Password:      password,
		Authenticated: true,
	})

	w.Write(ldapserver.NewBindResponse(ldapserver.LDAPResultSuccess))
}

// HandleSearch 處理通訊錄查詢（RootDSE 回應、GC 轉發、白名單過濾與審計）
func (s *ProxyServer) HandleSearch(w ldapserver.ResponseWriter, m *ldapserver.Message) {
	r := m.GetSearchRequest()
	baseObject := string(r.BaseObject())
	scope := int(r.Scope())
	filterStr := r.FilterString()

	clientAddr := ""
	if m.Client != nil && m.Client.Addr() != nil {
		clientAddr = m.Client.Addr().String()
	}

	session := s.getSession(clientAddr)

	// 1. RootDSE 探測快速回應 (Outlook / 系統探測)
	if baseObject == "" && scope == ldapserver.SearchRequestScopeBaseObject {
		s.logAudit("[ROOT_DSE] client=%s probe accepted", clientAddr)
		entry := ldapserver.NewSearchResultEntry("")
		entry.AddAttribute(message.AttributeDescription("subschemaSubentry"), message.AttributeValue("CN=Aggregate,CN=Schema,CN=Configuration,"+s.cfg.SearchBase))
		entry.AddAttribute(message.AttributeDescription("defaultNamingContext"), message.AttributeValue(s.cfg.SearchBase))
		entry.AddAttribute(message.AttributeDescription("namingContexts"), message.AttributeValue(s.cfg.SearchBase))
		entry.AddAttribute(message.AttributeDescription("supportedLDAPVersion"), message.AttributeValue("3"))
		entry.AddAttribute(message.AttributeDescription("supportedCapabilities"), message.AttributeValue("1.2.840.113556.1.4.800"))
		w.Write(entry)
		w.Write(ldapserver.NewSearchResultDoneResponse(ldapserver.LDAPResultSuccess))
		return
	}

	// 2. 確定連線後端身份
	backendConn, err := s.getBackendGC()
	if err != nil {
		s.logAudit("[SEARCH_ERROR_BACKEND] client=%s err=%v", clientAddr, err)
		w.Write(ldapserver.NewSearchResultDoneResponse(ldapserver.LDAPResultOperationsError))
		return
	}
	defer backendConn.Close()

	if session != nil && session.Authenticated && session.Username != "" && session.Password != "" {
		targetUser := session.UserUPN
		if targetUser == "" {
			targetUser = session.Username
		}
		_ = backendConn.Bind(targetUser, session.Password)
	} else if s.cfg.BindDN != "" {
		_ = backendConn.Bind(s.cfg.BindDN, s.cfg.BindPW)
	}

	searchBase := baseObject
	if searchBase == "" {
		searchBase = s.cfg.SearchBase
	}

	sizeLimit := int(r.SizeLimit())
	if sizeLimit <= 0 || sizeLimit > 1000 {
		sizeLimit = 500
	}

	timeLimit := int(r.TimeLimit())
	if timeLimit <= 0 {
		timeLimit = 30
	}

	if filterStr == "" {
		filterStr = "(objectClass=*)"
	}

	// 僅轉發白名單允許之屬性
	var backendAttrs []string
	reqAttrs := r.Attributes()
	if len(reqAttrs) > 0 {
		for _, attr := range reqAttrs {
			attrName := string(attr)
			if s.isAllowedAttr(attrName) {
				backendAttrs = append(backendAttrs, attrName)
			}
		}
	}
	if len(backendAttrs) == 0 {
		backendAttrs = s.cfg.AllowedAttrs
	}

	searchReq := ldap.NewSearchRequest(
		searchBase,
		scope,
		ldap.NeverDerefAliases,
		sizeLimit,
		timeLimit,
		false,
		filterStr,
		backendAttrs,
		nil,
	)

	sr, err := backendConn.Search(searchReq)
	if err != nil {
		s.logAudit("[SEARCH_FAIL] client=%s filter=%q err=%v", clientAddr, filterStr, err)
		w.Write(ldapserver.NewSearchResultDoneResponse(ldapserver.LDAPResultOperationsError))
		return
	}

	// 3. 過濾敏感屬性並回傳白名單通訊錄欄位
	returnedCount := 0
	for _, beEntry := range sr.Entries {
		resEntry := ldapserver.NewSearchResultEntry(beEntry.DN)
		for _, attr := range beEntry.Attributes {
			if !s.isAllowedAttr(attr.Name) {
				continue
			}
			var vals []message.AttributeValue
			for _, v := range attr.Values {
				vals = append(vals, message.AttributeValue(v))
			}
			resEntry.AddAttribute(message.AttributeDescription(attr.Name), vals...)
		}
		w.Write(resEntry)
		returnedCount++
	}

	w.Write(ldapserver.NewSearchResultDoneResponse(ldapserver.LDAPResultSuccess))

	// 4. 寫入企業審計日誌
	username := "anonymous"
	if session != nil && session.Username != "" {
		username = session.Username
	}
	s.logAudit("[SEARCH] client=%s user=%q base=%q filter=%q entries=%d",
		clientAddr, username, searchBase, filterStr, returnedCount)
}

// Start 啟動 TLS 3269 監聽服務
func (s *ProxyServer) Start() error {
	routes := ldapserver.NewRouteMux()
	routes.Bind(s.HandleBind)
	routes.Search(s.HandleSearch)

	server := ldapserver.NewServer()
	server.Handle(routes)
	s.server = server
	s.isRunning = true

	s.logAudit("[PROXY_START] Listening on TLS %s (Cert: %s, Key: %s)",
		s.cfg.ListenAddr, s.cfg.CertFile, s.cfg.KeyFile)

	// 確保憑證可用
	cert, err := tls.LoadX509KeyPair(s.cfg.CertFile, s.cfg.KeyFile)
	if err != nil {
		return fmt.Errorf("failed to load TLS key pair (%s, %s): %w", s.cfg.CertFile, s.cfg.KeyFile, err)
	}

	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS12,
	}

	return server.ListenAndServe(s.cfg.ListenAddr, func(srv *ldapserver.Server) {
		srv.Listener = tls.NewListener(srv.Listener, tlsConfig)
	})
}

// Stop 停止伺服器
func (s *ProxyServer) Stop() {
	if s.server != nil && s.isRunning {
		s.server.Stop()
		s.isRunning = false
		s.logAudit("[PROXY_STOP] LDAPS GAL Proxy stopped")
	}
	if s.logFile != nil {
		_ = s.logFile.Close()
	}
}
