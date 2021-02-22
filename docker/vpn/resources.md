https://r-pufky.github.io/docs/services/wireguard/windows-setup.html

https://download.wireguard.com/windows-client/



Start-Process msiexec.exe -ArgumentList '/q', '/I', 'wireguard-amd64-0.1.0.msi' -Wait -NoNewWindow -PassThru | Out-Null
Start-Process 'C:\Program Files\WireGuard\wireguard.exe' -ArgumentList '/uninstallmanagerservice' -Wait -NoNewWindow -PassThru | Out-Null



Start-Process 'C:\Program Files\WireGuard\wireguard.exe' -ArgumentList '/installtunnelservice', 'my-tunnel.conf' -Wait -NoNewWindow -PassThru | Out-Null
Start-Process sc.exe -ArgumentList 'config', 'WireGuardTunnel$my-tunnel', 'start= delayed-auto' -Wait -NoNewWindow -PassThru | Out-Null
Start-Service -Name WireGuardTunnel$my-tunnel -ErrorAction SilentlyContinue
