#!/bin/sh
## setup command=rm -rf /tmp/XStreamity-master /tmp/XStreamity-master.tar.gz; wget -q https://codeload.github.com/kiddac/XStreamity/tar.gz/refs/heads/master -O /tmp/XStreamity-master.tar.gz && tar -xzf /tmp/XStreamity-master.tar.gz -C /tmp && /bin/sh /tmp/XStreamity-master/installer.sh

description="
What is new:
- Fixed a potential crash on XKlass interface if ok button pressed too quickly
"

PLUGINPATH=/usr/lib/enigma2/python/Plugins/Extensions/XStreamity
TMPDIR=/tmp/XStreamity_update
ARCHIVE_ROOT=XStreamity-master/XStreamity
ARCHIVE_URL=https://codeload.github.com/kiddac/XStreamity/tar.gz/refs/heads/master

echo " ** Download and install XStreamity ** "
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR"
cd "$TMPDIR" || exit 1

# GNU wget and newer BusyBox builds support this option, but old VTi BusyBox
# builds do not. Only add it when the installed wget advertises support.
WGET_CERT_OPTION=
if wget --help 2>&1 | grep -q 'no-check-certificate'; then
    WGET_CERT_OPTION=--no-check-certificate
fi

if ! wget $WGET_CERT_OPTION -q "$ARCHIVE_URL" -O master.tar.gz \
   || ! tar -xzf master.tar.gz \
   || [ ! -f "$ARCHIVE_ROOT/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/plugin.py" ]; then
    echo "Download failed. Nothing was changed."
    cd /tmp
    rm -rf "$TMPDIR"
    exit 1
fi

# Never install bytecode built by a different Python version.
find "$ARCHIVE_ROOT/usr" -name '*.py[co]' -exec rm -f {} \; 2>/dev/null
find "$ARCHIVE_ROOT/usr" -type d -name '__pycache__' -prune -exec rm -rf {} \; 2>/dev/null

if ! cp -r "$ARCHIVE_ROOT/usr" /; then
    echo "Copying the files failed. Run the installer again."
    cd /tmp
    rm -rf "$TMPDIR"
    exit 1
fi

# Remove stale bytecode and let the receiver rebuild it after restart.
find "$PLUGINPATH" -name '*.py[co]' -exec rm -f {} \; 2>/dev/null
find "$PLUGINPATH" -type d -name '__pycache__' -prune -exec rm -rf {} \; 2>/dev/null

cd /tmp
rm -rf "$TMPDIR"

if [ ! -f "$PLUGINPATH/plugin.py" ]; then
    echo "XStreamity was not installed correctly."
    exit 1
fi

sync
echo
echo "XStreamity installed successfully. Restart Enigma2 to load the update."
exit 0
