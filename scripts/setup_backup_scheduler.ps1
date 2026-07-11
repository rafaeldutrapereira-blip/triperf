# LabX — Configurar backup automático diario en Windows Task Scheduler
# Ejecutar como Administrador:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_backup_scheduler.ps1

$TaskName     = "LabX-DailyBackup"
$ProjectDir   = "C:\Users\rafae\projects\LabX"
$PythonExe    = "C:\Users\rafae\AppData\Local\Programs\Python\Python312-arm64\python.exe"
$LogFile      = "$ProjectDir\logs\backup.log"
$BackupScript = "$ProjectDir\backup.py"

# Crear directorio de logs si no existe
New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

# Eliminar tarea existente si hay una
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[INFO] Tarea anterior eliminada."
}

# Configurar la acción
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "$BackupScript >> $LogFile 2>&1" `
    -WorkingDirectory $ProjectDir

# Ejecutar diariamente a las 02:00
$Trigger = New-ScheduledTaskTrigger -Daily -At "02:00"

# Configuración de la tarea
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false

# Registrar la tarea
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "LabX daily database backup at 02:00" `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "[OK] Tarea '$TaskName' registrada. Backup diario a las 02:00."
Write-Host "[OK] Log: $LogFile"
Write-Host ""
Write-Host "Para verificar:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Format-List"
Write-Host "Para ejecutar manualmente ahora:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
