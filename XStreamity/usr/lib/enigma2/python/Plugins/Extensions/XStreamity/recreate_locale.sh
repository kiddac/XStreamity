#!/bin/bash

set -e

SCRIPTDIR=$(dirname $BASH_SOURCE)

# create pot file with all translatable messages
(
    set -x
    #xgettext --language=Python --keyword=_ --output=$SCRIPTDIR/locale/en/LC_MESSAGES/XStreamity.pot $SCRIPTDIR/*.py
    pygettext3 -d messages -o $SCRIPTDIR/locale/en/LC_MESSAGES/XStreamity.pot $SCRIPTDIR/*.py
)


# create PO files
for LANG in $(ls locale); do
(
    set -x
    #msginit --input=$SCRIPTDIR/locale/en/LC_MESSAGES/XStreamity.pot --locale=$LANG --output-file=$SCRIPTDIR/locale/$LANG/LC_MESSAGES/XStreamity.po
    msgmerge --update $SCRIPTDIR/locale/$LANG/LC_MESSAGES/XStreamity.po $SCRIPTDIR/locale/en/LC_MESSAGES/XStreamity.pot

    msgfmt $SCRIPTDIR/locale/$LANG/LC_MESSAGES/XStreamity.po -o $SCRIPTDIR/locale/$LANG/LC_MESSAGES/XStreamity.mo

    rm -f "$SCRIPTDIR/locale/$LANG/LC_MESSAGES/XStreamity.po~"
)
done

echo "Done!"
