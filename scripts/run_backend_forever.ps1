# LabX — mantiene el backend (uvicorn) corriendo indefinidamente (reinicia solo si se cae)
$log = "C:\Users\rafae\projects\LabX\_uvicorn.log"
Set-Location "C:\Users\rafae\projects\LabX"

while ($true) {
    "$(Get-Date -Format o) [supervisor] arrancando uvicorn" | Out-File -Append -FilePath $log -Encoding utf8
    & python -m uvicorn api.coach_main:app --host 0.0.0.0 --port 8000 *>> $log
    "$(Get-Date -Format o) [supervisor] backend se cerro (exit=$LASTEXITCODE) - reintentando en 5s" | Out-File -Append -FilePath $log -Encoding utf8
    Start-Sleep -Seconds 5
}
