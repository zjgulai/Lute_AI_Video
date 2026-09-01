#!/bin/sh
set -eu

readonly UPSTREAM_VERSION="7.1.5"
readonly DEBIAN_VERSION="7:7.1.5-0+deb13u1"
readonly H10_VERSION="7:7.1.5-0+deb13u1+h10.5"
readonly SOURCE_ROOT="/opt/ffmpeg"
readonly BUILD_ROOT="/build/ffmpeg"
readonly OUTPUT_ROOT="/ffmpeg-debs"
readonly PATCH_NAME="86708357d126af84c16f80d9c57335d1e8c845c5.patch"
readonly DVBSUB_PATCH_NAME="02fc47e13f903768b75f7985a2706a6223ab4506.patch"
readonly CFHD_PATCH_NAME="16b2049d4d5222db6cd7c031409058571c94f6a9.patch"
readonly MPEGENC_PATCH_NAME="9d786e4b5e9b8482651928574de33772aeee7be1.patch"
readonly LIBRIST_PATCH_NAME="1c10bcc2e17255dacb717a25ab3db142ce390602.patch"
readonly VC2HQ_PATCH_NAME="1cdeb3c4e7f1f8566d846b9b451e01c376398818.patch"
readonly DASH_PATCH_NAME="65b0dab903e5975e036b30ecc58f5935d4f151e0-debian-7.1.5-backport.patch"
readonly ORIGINAL_SOURCE_SHA256="de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f"
readonly DEBIAN_SOURCE_SHA256="a1be51d8a10744952fe94fa318bf71bbc8074bed0951382c079ab7ef227f74ef"
readonly PATCH_SHA256="b800c259300e41ba3a35a626953ca7665648e7de9955e168d8477d7414e7e3f1"
readonly DVBSUB_PATCH_SHA256="6a06c12bab05882f3116b32e81562750c450a421d23635aaf25bddd254a80525"
readonly CFHD_PATCH_SHA256="dd5ab52749f5aabbdf02202d0bd26703079261cd429a0f6e6013299d6d468646"
readonly MPEGENC_PATCH_SHA256="2dcfec279bad372be7eb54b55f5f2c59b1c33151325317946b92da4e95039f34"
readonly LIBRIST_PATCH_SHA256="89554690fc735a902724168084150ec7b4631e42d525bd9a86b31dc5e8df8573"
readonly VC2HQ_PATCH_SHA256="849f908e6336d4b9676521c7e3405d18ef54b9b8800e58d9030ecb343868e03b"
readonly DASH_PATCH_SHA256="393142cc01e241019986194cb15b9d248b5173ccc45e23c1724ebc5f59fd73f5"
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
    "$DVBSUB_PATCH_SHA256" "$SOURCE_ROOT/$DVBSUB_PATCH_NAME" \
    "$CFHD_PATCH_SHA256" "$SOURCE_ROOT/$CFHD_PATCH_NAME" \
    "$MPEGENC_PATCH_SHA256" "$SOURCE_ROOT/$MPEGENC_PATCH_NAME" \
    "$LIBRIST_PATCH_SHA256" "$SOURCE_ROOT/$LIBRIST_PATCH_NAME" \
    "$VC2HQ_PATCH_SHA256" "$SOURCE_ROOT/$VC2HQ_PATCH_NAME" \
    "$DASH_PATCH_SHA256" "$SOURCE_ROOT/$DASH_PATCH_NAME" \
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
  for patch_name in \
    "$PATCH_NAME" \
    "$DVBSUB_PATCH_NAME" \
    "$CFHD_PATCH_NAME" \
    "$MPEGENC_PATCH_NAME" \
    "$LIBRIST_PATCH_NAME" \
    "$VC2HQ_PATCH_NAME" \
    "$DASH_PATCH_NAME"; do
    cp "$SOURCE_ROOT/$patch_name" "$BUILD_ROOT/debian/patches/$patch_name"
    grep -qxF "$patch_name" "$BUILD_ROOT/debian/patches/series" \
      || printf '%s\n' "$patch_name" >> "$BUILD_ROOT/debian/patches/series"
  done

  sed -i \
    "1s/(${DEBIAN_VERSION})/(${H10_VERSION})/" \
    "$BUILD_ROOT/debian/changelog"
  sed -i \
    '3i\  * H10: backport IAMF, DVB subtitle, CFHD, MPEG-PS, librist, VC-2 RTP, and DASH fixes; disable IAMF, libssh/SFTP, and librist/RIST.' \
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
  export SOURCE_DATE_EPOCH="1785845515"
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
