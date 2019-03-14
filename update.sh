#!/bin/bash
SCRIPTPATH=$( cd $(dirname $0) ; pwd -P );
SELF=`basename $0`;

echo "Wechsle ins Verzeichniss ($SCRIPTPATH) dieses Skripts"
cd $SCRIPTPATH;
git reset --hard HEAD;
git pull git://xeon.lan/mqttRaspberry;
exit $?