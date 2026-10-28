<#
.SYNOPSIS
Backs up or restores a Supabase database and optionally syncs the backup to Google Drive.
#>
param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("Backup", "Restore")]
    [string]$Action,

    [string]$ConfigFile = ".\config.json",
    [string]$RestoreFilePath = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ConfigFile)) {
    Write-Error "Configuration file not found at $ConfigFile"
    exit 1
}

$config = Get-Content $ConfigFile | ConvertFrom-Json
$dbUrl = $config.DatabaseUrl

if ($Action -eq "Backup") {
    $backupDir = $config.BackupDirectory
    if (-not (Test-Path $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $backupDir "supabase_backup_$timestamp.dump"

    Write-Host "Starting local database backup to $backupFile..."
    # -F c specifies custom format, which is required for targeted Supabase restorations
    pg_dump --clean --if-exists -F c -f $backupFile $dbUrl
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pg_dump failed with exit code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
    Write-Host "Local backup completed."

    if ($config.GoogleDrive.Enabled) {
        Write-Host "Uploading to Google Drive..."
        $gd = $config.GoogleDrive
        
        # 1. Exchange refresh token for an active access token
        $tokenParams = @{
            Uri = 'https://oauth2.googleapis.com/token'
            Method = 'Post'
            ContentType = 'application/x-www-form-urlencoded'
            Body = @{
                client_id     = $gd.ClientId
                client_secret = $gd.ClientSecret
                refresh_token = $gd.RefreshToken
                grant_type    = 'refresh_token'
            }
        }
        
        try {
            $accessToken = (Invoke-RestMethod @tokenParams).access_token
        } catch {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $googleError = $reader.ReadToEnd()
            Write-Error "Google OAuth Error: $googleError"
            exit 1
        }

        # 2. Upload file content (Uses -InFile to stream directly from disk without maxing out RAM)
        $uploadUri = "https://www.googleapis.com/upload/drive/v3/files?uploadType=media"
        $uploadHeaders = @{
            "Authorization" = "Bearer $accessToken"
            "Content-Type"  = "application/octet-stream"
        }
        $uploadResponse = Invoke-RestMethod -Uri $uploadUri -Method Post -Headers $uploadHeaders -InFile $backupFile

        # 3. Update the blank file metadata with the correct filename and Drive folder
        $patchUri = "https://www.googleapis.com/drive/v3/files/$($uploadResponse.id)"
        if ($gd.FolderId) {
            $patchUri += "?addParents=$($gd.FolderId)"
        }
        
        $patchHeaders = @{
            "Authorization" = "Bearer $accessToken"
            "Content-Type"  = "application/json"
        }
        $patchBody = @{
            name = (Split-Path $backupFile -Leaf)
        } | ConvertTo-Json

        Invoke-RestMethod -Uri $patchUri -Method Patch -Headers $patchHeaders -Body $patchBody | Out-Null
        
        Write-Host "Upload completed successfully. Google Drive File ID: $($uploadResponse.id)"
    }
}
elseif ($Action -eq "Restore") {
    if (-not $RestoreFilePath) {
        Write-Error "Please provide the path to the backup file using -RestoreFilePath"
        exit 1
    }
    if (-not (Test-Path $RestoreFilePath)) {
        Write-Error "Restore file not found at $RestoreFilePath"
        exit 1
    }

    Write-Host "Restoring database from $RestoreFilePath..."
    
    # Supressing ownership prevents standard pg_restore errors when interacting with Supabase's managed auth schemas
    pg_restore --clean --if-exists --no-owner --no-privileges -d $dbUrl $RestoreFilePath
    
    Write-Host "Restore operation finished. (Note: Output warnings regarding Supabase managed extensions like 'auth' or 'graphql' are normal and expected)."
}