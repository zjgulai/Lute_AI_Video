#!/bin/sh
set -eu

readonly UPSTREAM_VERSION="7.1.5"
readonly DEBIAN_VERSION="7:7.1.5-0+deb13u1"
readonly H10_VERSION="7:7.1.5-0+deb13u1+h10.3"
readonly SOURCE_ROOT="/opt/ffmpeg"
readonly BUILD_ROOT="/build/ffmpeg"
readonly OUTPUT_ROOT="/ffmpeg-debs"
readonly PATCH_NAME="86708357d126af84c16f80d9c57335d1e8c845c5.patch"
readonly ORIGINAL_SOURCE_SHA256="de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f"
readonly DEBIAN_SOURCE_SHA256="a1be51d8a10744952fe94fa318bf71bbc8074bed0951382c079ab7ef227f74ef"
readonly PATCH_SHA256="b800c259300e41ba3a35a626953ca7665648e7de9955e168d8477d7414e7e3f1"
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

verify_inputs() {
  printf '%s  %s\n' \
    "$ORIGINAL_SOURCE_SHA256" "$SOURCE_ROOT/ffmpeg_${UPSTREAM_VERSION}.orig.tar.xz" \
    "$DEBIAN_SOURCE_SHA256" "$SOURCE_ROOT/ffmpeg_${UPSTREAM_VERSION}-0+deb13u1.debian.tar.xz" \
    "$PATCH_SHA256" "$SOURCE_ROOT/$PATCH_NAME" \
    | sha256sum -c -
}

prepare_source() {
  mkdir -p "$BUILD_ROOT" "$OUTPUT_ROOT"
  tar -xf "$SOURCE_ROOT/ffmpeg_${UPSTREAM_VERSION}.orig.tar.xz" \
    -C "$BUILD_ROOT" --strip-components=1
  tar -xf "$SOURCE_ROOT/ffmpeg_${UPSTREAM_VERSION}-0+deb13u1.debian.tar.xz" \
    -C "$BUILD_ROOT"

  mkdir -p "$BUILD_ROOT/debian/patches"
  touch "$BUILD_ROOT/debian/patches/series"
  cp "$SOURCE_ROOT/$PATCH_NAME" "$BUILD_ROOT/debian/patches/$PATCH_NAME"
  grep -qxF "$PATCH_NAME" "$BUILD_ROOT/debian/patches/series" \
    || printf '%s\n' "$PATCH_NAME" >> "$BUILD_ROOT/debian/patches/series"

  sed -i \
    "1s/(${DEBIAN_VERSION})/(${H10_VERSION})/" \
    "$BUILD_ROOT/debian/changelog"
  sed -i \
    '3i\  * H10: backport IAMF fix; disable IAMF, libssh/SFTP, and librist/RIST.' \
    "$BUILD_ROOT/debian/changelog"
  printf '\n# H10 defense in depth: the application never accepts IAMF.\n' \
    >> "$BUILD_ROOT/debian/rules"
  printf 'CONFIG += --disable-demuxer=iamf --disable-libssh --disable-librist --disable-debug\n' \
    >> "$BUILD_ROOT/debian/rules"
  sed -i \
    's/^FLAVORS = standard static$/FLAVORS = standard/' \
    "$BUILD_ROOT/debian/rules"
}

build_packages() {
  cd "$BUILD_ROOT"
  export DEB_BUILD_OPTIONS="${DEB_BUILD_OPTIONS:+$DEB_BUILD_OPTIONS }nocheck noautodbgsym"
  export DEB_CFLAGS_MAINT_APPEND="${DEB_CFLAGS_MAINT_APPEND:+$DEB_CFLAGS_MAINT_APPEND }-g0"
  export DEB_CXXFLAGS_MAINT_APPEND="${DEB_CXXFLAGS_MAINT_APPEND:+$DEB_CXXFLAGS_MAINT_APPEND }-g0"
  export SOURCE_DATE_EPOCH="1782677128"
  dpkg-buildpackage -B -Ppkg.ffmpeg.noextra -uc -us -j"$(nproc)"
}

collect_runtime_packages() {
  for package in $RUNTIME_PACKAGES; do
    candidates="$(find /build -maxdepth 1 -type f \
      -name "${package}_*.deb" ! -name '*-dbgsym_*' -print)"
    count="$(printf '%s\n' "$candidates" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$count" -ne 1 ]; then
      printf 'expected one package for %s, found %s\n' "$package" "$count" >&2
      exit 1
    fi
    candidate="$candidates"
    test "$(dpkg-deb -f "$candidate" Package)" = "$package"
    test "$(dpkg-deb -f "$candidate" Version)" = "$H10_VERSION"
    cp "$candidate" "$OUTPUT_ROOT/"
  done
  test "$(find "$OUTPUT_ROOT" -maxdepth 1 -type f -name '*.deb' | wc -l | tr -d ' ')" -eq 9
}

verify_inputs
prepare_source
build_packages
collect_runtime_packages
