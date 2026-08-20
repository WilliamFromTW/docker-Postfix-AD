-- /etc/rspamd/local.d/quarantine_redirect.lua
rspamd_config:register_symbol({
  name = 'QUARANTINE_REDIRECT',
  type = 'postfilter',
  priority = 10,
  callback = function(task)
    local action = task:get_metric_action()

    -- 當 Rspamd 計算出的動作為 reject 時介入
    if action == 'reject' then
      local quarantine_target = 'SPAM_EMAIL'

      -- 將 SMTP 信封收件人重寫為隔離集中區信箱
      task:set_recipients('smtp', {quarantine_target}, 'rewrite')

      -- 將動作重設為 accept，避免向 MTA 觸發 5xx 錯誤回應
      task:set_pre_result('accept', 'Message quarantined silently')

      -- 注入自訂標頭供後續審計
      task:set_milter_reply({
        add_headers = {
          ['X-Quarantine-Original-Action'] = 'reject',
          ['X-Quarantine-Reason'] = 'High spam score'
        }
      })
    end
  end
})

