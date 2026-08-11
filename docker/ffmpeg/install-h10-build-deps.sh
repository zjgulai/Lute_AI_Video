#!/bin/sh
set -eu

readonly DEBIAN_VERSION="7:7.1.5-0+deb13u1"

if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed -i "s|deb.debian.org|${APT_MIRROR:-deb.debian.org}|g" \
    /etc/apt/sources.list.d/debian.sources
  sed -i 's/^Types: deb$/Types: deb deb-src/' \
    /etc/apt/sources.list.d/debian.sources
fi
if [ -f /etc/apt/sources.list ]; then
  sed -i "s|deb.debian.org|${APT_MIRROR:-deb.debian.org}|g" \
    /etc/apt/sources.list
fi

export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::Retries=5 update
apt-get install -y --no-install-recommends \
  build-essential \
  ca-certificates \
  dpkg-dev \
  fakeroot \
  patch \
  quilt
apt-get build-dep -y --no-install-recommends "ffmpeg=${DEBIAN_VERSION}"
rm -rf /var/lib/apt/lists/*
