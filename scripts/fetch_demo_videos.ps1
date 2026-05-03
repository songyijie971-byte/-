param(
    [string]$OutputDir = "samples\demo_videos",
    [int]$Seconds = 10,
    [int]$Width = 1280,
    [int]$Crf = 26
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    $knownPath = "D:\merge\merge\path\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
    if (Test-Path $knownPath) {
        $ffmpeg = $knownPath
    }
}
if (-not $ffmpeg) {
    throw "ffmpeg was not found in PATH. Install ffmpeg or update this script with its path."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$videos = @(
    @{
        Id = "6672356"
        File = "01_mixed_classroom_lowhead_phone_raisinghand.mp4"
        Scale = "scale=$($Width):-2"
    },
    @{
        Id = "5897637"
        File = "02_single_student_raising_hand.mp4"
        Scale = "scale=-2:720"
    },
    @{
        Id = "8419400"
        File = "03_classroom_discussion_turntalk.mp4"
        Scale = "scale=$($Width):-2"
    },
    @{
        Id = "4769542"
        File = "04_tired_student_sleep_like_pose.mp4"
        Scale = "scale=$($Width):-2"
    },
    @{
        Id = "8617299"
        File = "05_group_students_raising_hands.mp4"
        Scale = "scale=$($Width):-2"
    }
)

foreach ($video in $videos) {
    $url = "https://www.pexels.com/download/video/$($video.Id)/"
    $output = Join-Path $OutputDir $video.File
    Write-Host "Fetching $($video.Id) -> $output"
    & $ffmpeg -hide_banner -y -ss 0 -t $Seconds -i $url -vf $video.Scale -an -c:v libx264 -preset veryfast -crf $Crf $output
}
