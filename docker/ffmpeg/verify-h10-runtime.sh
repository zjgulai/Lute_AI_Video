#!/bin/sh
set -eu

readonly EXPECTED_VERSION="7:7.1.5-0+deb13u1+h10.3"
readonly RUNTIME_PACKAGES="
ffmpeg
libavcodec61
libavdevice61
libavfilter10
libavformat61
libavutil59
libpostproc58
libswresample5
libswscale8
"

for package in $RUNTIME_PACKAGES; do
  actual="$(dpkg-query -W -f='${Version}' "$package")"
  if [ "$actual" != "$EXPECTED_VERSION" ]; then
    printf 'unexpected %s version: %s\n' "$package" "$actual" >&2
    exit 1
  fi
done

for forbidden_package in libssh-4 librist4 libcjson1; do
  if dpkg-query -W "$forbidden_package" >/dev/null 2>&1; then
    printf '%s must not be installed\n' "$forbidden_package" >&2
    exit 1
  fi
done

if ! ffmpeg_inventory="$(ffmpeg -hide_banner -demuxers 2>/dev/null)"; then
  printf 'ffmpeg demuxer inventory failed\n' >&2
  exit 1
fi
if [ -z "$ffmpeg_inventory" ]; then
  printf 'ffmpeg demuxer inventory is empty\n' >&2
  exit 1
fi
if printf '%s\n' "$ffmpeg_inventory" \
  | awk '$2 == "iamf" { found = 1 } END { exit(found ? 0 : 1) }'; then
  printf 'IAMF demuxer remains enabled in ffmpeg\n' >&2
  exit 1
fi

if ! ffprobe_inventory="$(ffprobe -hide_banner -formats 2>/dev/null)"; then
  printf 'ffprobe format inventory failed\n' >&2
  exit 1
fi
if [ -z "$ffprobe_inventory" ]; then
  printf 'ffprobe format inventory is empty\n' >&2
  exit 1
fi
if printf '%s\n' "$ffprobe_inventory" \
  | awk '$2 == "iamf" && index($1, "D") { found = 1 } END { exit(found ? 0 : 1) }'; then
  printf 'IAMF demuxer remains enabled in ffprobe\n' >&2
  exit 1
fi

if ! protocol_inventory="$(ffmpeg -hide_banner -protocols 2>/dev/null)"; then
  printf 'ffmpeg protocol inventory failed\n' >&2
  exit 1
fi
if [ -z "$protocol_inventory" ]; then
  printf 'ffmpeg protocol inventory is empty\n' >&2
  exit 1
fi
if printf '%s\n' "$protocol_inventory" \
  | awk '$1 == "sftp" { found = 1 } END { exit(found ? 0 : 1) }'; then
  printf 'SFTP protocol remains enabled\n' >&2
  exit 1
fi
if printf '%s\n' "$protocol_inventory" \
  | awk '$1 == "rist" { found = 1 } END { exit(found ? 0 : 1) }'; then
  printf 'RIST protocol remains enabled\n' >&2
  exit 1
fi

ffmpeg_deb="$(find /tmp/ffmpeg-debs -maxdepth 1 -type f \
  -name 'ffmpeg_*_amd64.deb' -print)"
test "$(printf '%s\n' "$ffmpeg_deb" | sed '/^$/d' | wc -l | tr -d ' ')" -eq 1
dpkg-deb --fsys-tarfile "$ffmpeg_deb" \
  | tar -xO ./usr/share/doc/ffmpeg/changelog.Debian.gz \
  | gzip -dc \
  | grep -Fq \
    'H10: backport IAMF fix; disable IAMF, libssh/SFTP, and librist/RIST.'
