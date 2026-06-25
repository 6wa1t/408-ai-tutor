param(
    [string]$InputDir = "D:\project code\408-ai-tutor-mineru\data\mineru_wangdao_input\questions",
    [string]$OutputDir = "D:\project code\408-ai-tutor-mineru\data\mineru_wangdao_output\questions_high_gpu"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$env:MINERU_API_MAX_CONCURRENT_REQUESTS = "1"
$env:MINERU_PROCESSING_WINDOW_SIZE = "16"

Write-Host "MinerU GPU extraction started: $(Get-Date -Format o)"
Write-Host "Input: $InputDir"
Write-Host "Output: $OutputDir"
Write-Host "MINERU_API_MAX_CONCURRENT_REQUESTS=$env:MINERU_API_MAX_CONCURRENT_REQUESTS"
Write-Host "MINERU_PROCESSING_WINDOW_SIZE=$env:MINERU_PROCESSING_WINDOW_SIZE"

mineru -p $InputDir -o $OutputDir -b hybrid-engine --effort high --image-analysis true -l ch

Write-Host "MinerU GPU extraction finished: $(Get-Date -Format o)"
