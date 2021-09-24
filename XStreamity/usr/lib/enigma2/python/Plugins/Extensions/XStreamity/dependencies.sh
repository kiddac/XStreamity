#!/bin/sh
pyv="$(python -V 2>&1)"
echo "$pyv"
echo "Checking Dependencies"
echo ""
if [ -d /etc/opkg ]; then
    echo "updating feeds"
    opkg update
    echo ""
    if [[ $pyv =~ "Python 3" ]]; then
        echo "checking python3-requests"
        opkg install python3-requests
        echo ""
    else
        echo "checking python-image"
        opkg install python-image
        echo ""
        echo "checking python-imaging"
        opkg install python-imaging
        echo ""
        echo "checking python-requests"
        opkg install python-requests
        echo ""
    fi
else
    echo "updating feeds"
    apt-get update
    echo ""
    if [[ $pyv =~ "Python 3" ]]; then
        echo "checking python3-requests"
        apt-get -y install python3-requests
        echo ""
    else
        echo "checking python-image"
        apt-get -y install python-image
        echo ""
        echo "checking python-imaging"
        apt-get -y install python-imaging
        echo ""
        echo "checking python-requests"
        apt-get -y install python-requests
        echo ""
    fi
fi
exit 0
