#!/bin/sh

pyv="$(python -V 2>&1)"
echo "$pyv"
echo "Checking Dependencies"
echo ""

fail=0  # Initialize fail variable

if [[ $pyv =~ "Python 3" ]]; then
    REQ_PKG="python3-requests"
    MULTIPROC_PKG="python3-multiprocessing"
    SIX_PKG="python3-six"
    PIL_PKG="python3-pillow"
else
    REQ_PKG="python-requests"
    MULTIPROC_PKG="python-multiprocessing"
    SIX_PKG="python-six"
    PIL_PKG="python-imaging"
fi

if [ -x "$(command -v apt-get)" ]; then
    PKG_INSTALL="apt-get -y install"
elif [ -x "$(command -v opkg)" ]; then
    PKG_INSTALL="opkg install"
else
    echo "Package manager not found. Exiting."
    exit 1
fi


echo "Checking $REQ_PKG"
if ! python -c "import requests"; then
    $PKG_INSTALL $REQ_PKG || { echo "Failed to install $REQ_PKG"; fail=1; }
fi
echo ""

echo "Checking $MULTIPROC_PKG"
if ! python -c "from multiprocessing.pool import ThreadPool"; then
    $PKG_INSTALL $MULTIPROC_PKG || { echo "Failed to install $MULTIPROC_PKG"; fail=1; }
fi
echo ""

echo "Checking $SIX_PKG"
if ! python -c "import six"; then
    $PKG_INSTALL $SIX_PKG || { echo "Failed to install $SIX_PKG"; fail=1; }
fi
echo ""

echo "Checking $PIL_PKG"
if ! python -c "from PIL import Image"; then
    $PKG_INSTALL $PIL_PKG || { echo "Failed to install $PIL_PKG"; fail=1; }
fi
echo ""

# Exit with non-zero code if any installation failed

echo "failure code: $fail"

if [ $fail -eq 1 ]; then
    exit 1
else
    exit 0
fi
