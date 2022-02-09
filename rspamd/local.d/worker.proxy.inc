# local.d/worker-proxy.inc
upstream "local" {
  self_scan = yes; # Enable self-scan
}

# Proxy worker is listening on *:11332 by default
bind_socket = localhost:11332;
