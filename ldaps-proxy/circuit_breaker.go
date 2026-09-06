package main

import (
	"fmt"
	"strings"
	"sync"
	"time"
)

// FailureRecord 記錄特定「來源 IP + 帳號」的失敗狀態與請求頻率
type FailureRecord struct {
	Failures      int
	LastFailAt    time.Time
	LastRequestAt time.Time
	BlockedUntil  time.Time
}

// CircuitBreaker 負責保護後端 Active Directory 免於帳號鎖定 (Anti-Lockout) 與短時間防抖
type CircuitBreaker struct {
	mu          sync.RWMutex
	records     map[string]*FailureRecord
	maxFailures int
	window      time.Duration
	cooldown    time.Duration
	maxEntries  int
}

// NewCircuitBreaker 建立新的防爆破熔斷器實例
func NewCircuitBreaker(maxFailures int, window time.Duration, cooldown time.Duration) *CircuitBreaker {
	if maxFailures <= 0 {
		maxFailures = 5
	}
	if window <= 0 {
		window = 5 * time.Minute
	}
	if cooldown <= 0 {
		cooldown = 30 * time.Second
	}

	cb := &CircuitBreaker{
		records:     make(map[string]*FailureRecord),
		maxFailures: maxFailures,
		window:      window,
		cooldown:    cooldown,
		maxEntries:  50000, // 預設上限追蹤 5 萬筆，鎖定記憶體 < 15MB 防止海量爆破 OOM
	}

	// 定期背景清理過期紀錄
	go cb.startCleaner()

	return cb
}

func (cb *CircuitBreaker) makeKey(clientIP, username string) string {
	ip := strings.TrimSpace(clientIP)
	// 去除 port
	if idx := strings.LastIndex(ip, ":"); idx != -1 && !strings.Contains(ip, "]") {
		ip = ip[:idx]
	}
	return fmt.Sprintf("%s:%s", ip, strings.ToLower(strings.TrimSpace(username)))
}

// IsBlocked 檢查特定來源 IP 與帳號當前是否處於熔斷阻斷狀態
func (cb *CircuitBreaker) IsBlocked(clientIP, username string) bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	key := cb.makeKey(clientIP, username)
	record, exists := cb.records[key]
	if !exists {
		return false
	}

	now := time.Now()
	// 若阻斷期未過
	if now.Before(record.BlockedUntil) {
		return true
	}

	// 若已過阻斷期，自動解除
	if !record.BlockedUntil.IsZero() && now.After(record.BlockedUntil) {
		delete(cb.records, key)
		return false
	}

	return false
}

// evictIfFullLocked 在容量達到上限時淘汰過期或舊紀錄 (呼叫方必須已持有 Lock)
func (cb *CircuitBreaker) evictIfFullLocked() {
	if cb.maxEntries <= 0 || len(cb.records) < cb.maxEntries {
		return
	}

	now := time.Now()
	// 1. 優先淘汰已過期或超出時間視窗的紀錄
	for k, rec := range cb.records {
		if !rec.BlockedUntil.IsZero() && now.After(rec.BlockedUntil) {
			delete(cb.records, k)
		} else if rec.BlockedUntil.IsZero() && now.Sub(rec.LastFailAt) > cb.window {
			delete(cb.records, k)
		}
	}

	// 2. 若依然達到上限，隨機淘汰最先遍歷到的 10% 項目騰出空間
	if len(cb.records) >= cb.maxEntries {
		targetEvict := cb.maxEntries / 10
		if targetEvict < 1 {
			targetEvict = 1
		}
		count := 0
		for k := range cb.records {
			delete(cb.records, k)
			count++
			if count >= targetEvict {
				break
			}
		}
	}
}

// SetMaxEntries 設定最大容量上限 (供測試或客製化)
func (cb *CircuitBreaker) SetMaxEntries(limit int) {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	if limit > 0 {
		cb.maxEntries = limit
	}
}

// CheckRateLimit 檢查短時間內同帳號是否發起過於頻繁的請求 (Debounce 防抖)
// 若請求間隔小於 minInterval，回傳 true 代表過於頻繁 (應回傳 Busy)
func (cb *CircuitBreaker) CheckRateLimit(clientIP, username string, minInterval time.Duration) bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	key := cb.makeKey(clientIP, username)
	now := time.Now()

	record, exists := cb.records[key]
	if !exists {
		cb.evictIfFullLocked()
		cb.records[key] = &FailureRecord{
			LastRequestAt: now,
		}
		return false
	}

	if !record.LastRequestAt.IsZero() && now.Sub(record.LastRequestAt) < minInterval {
		return true
	}

	record.LastRequestAt = now
	return false
}

// RecordFailure 記錄一次密碼或身分驗證失敗，若達到上限回傳 true 代表已觸發熔斷
func (cb *CircuitBreaker) RecordFailure(clientIP, username string) bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	key := cb.makeKey(clientIP, username)
	now := time.Now()

	record, exists := cb.records[key]
	if !exists {
		cb.evictIfFullLocked()
		cb.records[key] = &FailureRecord{
			Failures:   1,
			LastFailAt: now,
		}
		return false
	}

	// 若上次失敗已超出時間視窗 (window)，重設計數器
	if now.Sub(record.LastFailAt) > cb.window {
		record.Failures = 1
		record.LastFailAt = now
		record.BlockedUntil = time.Time{}
		return false
	}

	record.Failures++
	record.LastFailAt = now

	// 檢查是否達到熔斷上限
	if record.Failures >= cb.maxFailures {
		record.BlockedUntil = now.Add(cb.cooldown)
		return true
	}

	return false
}

// RecordSuccess 登入成功時清除此鍵之所有失敗歷史
func (cb *CircuitBreaker) RecordSuccess(clientIP, username string) {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	key := cb.makeKey(clientIP, username)
	delete(cb.records, key)
}

func (cb *CircuitBreaker) startCleaner() {
	ticker := time.NewTicker(5 * time.Minute)
	for range ticker.C {
		cb.mu.Lock()
		now := time.Now()
		for k, rec := range cb.records {
			// 若冷卻已結束且最近失敗已逾時，清除
			if !rec.BlockedUntil.IsZero() && now.After(rec.BlockedUntil) {
				delete(cb.records, k)
			} else if rec.BlockedUntil.IsZero() && now.Sub(rec.LastFailAt) > cb.window {
				delete(cb.records, k)
			}
		}
		cb.mu.Unlock()
	}
}
