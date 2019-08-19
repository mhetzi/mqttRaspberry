#!/bin/bash
SCRIPTPATH=$( cd $(dirname $0) ; pwd -P );
SELF=`basename $0`;
username=$(whoami);

python3 -c "import sys, pkgutil; sys.exit(0 if pkgutil.find_loader('virtualenv') else 1)"
hasVenvInstalled=$?;

echo "Virtalenv installed? $hasVenvInstalled"
echo "Parameter übergeben: $1"


install() {
    echo $1
    sudo bash -c "mkdir -p /opt/mqttScripts/config/ ; chown $username /opt/mqttScripts/ -Rv;"
    cd /opt/mqttScripts/
    if [[ $hasVenvInstalled -eq 1 ]]; then
        read -p "virtualenvironments nicht installiert. Installieren? " -n 1 -r
        if [[ $REPLY =~ ^[YyJj]$ ]]
        then
            sudo bash -c "sudo apt update; sudo apt install python3-pip python3-dev libatlas-base-dev libjpeg9-dev libfreetype6-dev -y; python3 -m pip install virtualenv; python3 -m pip install --upgrade virtualenv"
        fi
    fi
    echo "Erselle VENV"
    python3 -m virtualenv venv --system-site-packages --clear
    echo "Aktivieren venv"
    source venv/bin/activate
    python3 -m pip install pip-review
    echo "mqttScripts wird heruntergeladen..."
    git clone git://xeon.lan/mqttRaspberry data
    echo "Repo geladen"
    read -p "Service aktivieren und starten? " -n 1 -r
    if [[ $REPLY =~ ^[YyJj]$ ]]
    then
        sudo bash -c "cp /opt/mqttScripts/data/mqttScript@.service /etc/systemd/system/; systemctl enable --now mqttScript@$username"
    fi
    
    exit 0
}
    

update() {
    #git reset --hard testing;
    git pull git://xeon.lan/mqttRaspberry;
    git reset --hard origin/master;
    git pull git://xeon.lan/mqttRaspberry;

    git pull git://xeon.lan/mqttRaspberry;
    git reset --hard origin/master;
    git pull git://xeon.lan/mqttRaspberry;
    
    local pullSuccess=$?

    if [[ $hasVenvInstalled -eq 0 ]]; then
        echo "update pip"
        source /opt/mqttScripts/venv/bin/activate
        pip-review -a --user
    fi
    return $pullSuccess
}

echo "Wechsle ins Verzeichniss ($SCRIPTPATH) dieses Skripts"
cd $SCRIPTPATH;
if [ "$1" == "update" ]
then
    update
    pullSuccess=$?
    exit $pullSuccess
fi

if [ "$1" == "update-full" ]
then
    #git reset --hard testing;
    update
    pullSuccess=$?
    sudo cp ./mqttScript@.service /etc/systemd/system/ -v
    sudo systemctl daemon-reload
    exit $pullSuccess
fi


if [ "$1" == "run-service" ]
then
    #git reset --hard testing;
    source /opt/mqttScripts/venv/bin/activate
    ./Launcher.py --systemd --config /opt/mqttScripts/config/mqttra.config
    exit $?
fi

if [ "$1" == "stop-service" ]
then
    #git reset --hard testing;
    echo "shutdown" > /opt/mqttScripts/signal.pipe
fi

if [ "$1" == "configure" ]
then
    #git reset --hard testing;
    source /opt/mqttScripts/venv/bin/activate
    ./Launcher.py --config /opt/mqttScripts/config/mqttra.config --configure
    exit $?
fi


if [ "$1" == "install" ]
then
    install;
fi

if [ "$1" == "reinstall" ]
then
    cd /opt/mqttScripts/
    rm -rfv data venv
    install;
fi

update