# LabX — mantiene cloudflared corriendo indefinidamente (reinicia solo si se cae)
# Usa el named tunnel "labx-prod" (config en C:\Users\rafae\.cloudflared\config.yml)
$exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = "C:\Users\rafae\projects\LabX\_cloudflared.log"

while ($true) {
    "$(Get-Date -Format o) [supervisor] arrancando cloudflared tunnel run labx-prod" | Out-File -Append -FilePath $log -Encoding utf8
    & $exe tunnel run labx-prod *>> $log
    "$(Get-Date -Format o) [supervisor] cloudflared se cerro (exit=$LASTEXITCODE) - reintentando en 5s" | Out-File -Append -FilePath $log -Encoding utf8
    Start-Sleep -Seconds 5
}
