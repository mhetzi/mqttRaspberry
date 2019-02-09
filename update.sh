#!/bin/bash
SCRIPTPATH=$( cd $(dirname $0) ; pwd -P );
SELF=`basename $0`;

cd SCRIPTPATH;
git pull git://xeon.lan/mqttRaspberry;