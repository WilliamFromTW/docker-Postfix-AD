-- /etc/rspamd/rspamd.local.lua
-- =========================================================================
-- 【說明】：Rspamd 原生自訂 Lua 啟動載入點。
-- Rspamd 主行程啟動時會自動載入此檔案，在此載入 kafeiou.d 的客製過濾腳本。
-- =========================================================================

-- 載入隔離重定向後處理過濾器 (Postfilter)
pcall(dofile, "/etc/rspamd/kafeiou.d/quarantine_redirect.lua")
