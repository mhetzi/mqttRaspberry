#!/bin/bash
SCRIPTPATH=$( cd $(dirname $0) ; pwd -P );
SELF=`basename $0`;
username=$(whoami);

python3 -c "import sys, pkgutil; sys.exit(0 if pkgutil.find_loader('virtualenv') else 1)"
hasVenvInstalled=$?;

echo "Virtalenv installed? $hasVenvInstalled"
echo "Parameter übergeben: $1"

install_user() {
    sudo cp /opt/mqttScripts/data/mqttScript.service /etc/systemd/user/mqttScript.service
    sudo bash -c "echo [Install] >> /etc/systemd/user/mqttScript.service"
    sudo bash -c "echo WantedBy=default.target >> /etc/systemd/user/mqttScript.service"
    systemctl enable --user mqttScript
    read -p "Service starten? " -n 1 -r
    if [[ $REPLY =~ ^[YyJj]$ ]]
    then
        systemctl start --user mqttScript
    fi
    read -p "PolKit rules installieren? " -n 1 -r
    if [[ $REPLY =~ ^[YyJj]$ ]]
    then
        sudo bash -c "cp /opt/mqttScripts/data/resources/mqttScripts_smart.rules /etc/polkit-1/rules.d/mqttScripts_smart.rules"
        echo "PolKit rules installiert"
    fi
}

install_system() {
    sudo bash -c "cp /opt/mqttScripts/data/mqttScript.service /etc/systemd/system/mqttScript@.service"
    sudo bash -c "echo User=%i >> /etc/systemd/system/mqttScript@.service"
    sudo bash -c "echo [Install] >> /etc/systemd/system/mqttScript@.service"
    sudo bash -c "echo WantedBy=multi-user.target >> /etc/systemd/system/mqttScript@.service"
    sudo bash -c "systemctl enable mqttScript@$username"
    read -p "Service starten? " -n 1 -r
    if [[ $REPLY =~ ^[YyJj]$ ]]
    then
        sudo bash -c "systemctl start mqttScript@$username"
    fi
}

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
    git clone git://xeon.lan/mqttRaspberry data || git clone https://github.com/mhetzi/mqttRaspberry.git data;
    echo "Repo geladen"
    read -p "Service aktivieren? " -n 1 -r
    if [[ $REPLY =~ ^[YyJj]$ ]]
    then
        echo "logind PLugin brauch zB Benutzerservice"
        read -p "Als [B]enutzerservice oder als [S]ystemservice installieren? " -n 1 -r
        if [[ $REPLY =~ ^[YyJjBb]$ ]]
        then
            install_user;
        else
            install_system;
        fi
    fi
    
    exit 0
}

update() {
    #git reset --hard testing;
    git pull ;
    git reset --hard origin/master;
    git pull ;

    git pull ;
    git reset --hard origin/master;
    git pull;
    
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

if [ "$1" == "run" ]
then
    #git reset --hard testing;
    source /opt/mqttScripts/venv/bin/activate
    ./Launcher.py --config /opt/mqttScripts/config/mqttra.config
    exit $?
fi

if [ "$1" == "stop-service" ]
then
    #git reset --hard testing;
    echo "shutdown" > /opt/mqttScripts/signal.pipe
fi

if [ "$1" == "configure" ]
then
    source /opt/mqttScripts/venv/bin/activate
    if [ -n "$2" ]
    then
        ./Launcher.py --config /opt/mqttScripts/config/mqttra.config --configure_plugin=$2
    else
        ./Launcher.py --config /opt/mqttScripts/config/mqttra.config --configure-all-plugins
    fi
    #git reset --hard testing;
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
    rmdir data venv
    install;
fi

update