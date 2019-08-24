# -*- coding: utf-8 -*-
import pathlib
import os.path as osp
import logging
import Tools.Autodiscovery as autodisc

try:
    import json
except ImportError:
    import simplejson as json

FILEWATCHING = False
try:
    from watchdog.observers import Observer
    import watchdog.events as watchevents

    FILEWATCHING = True
except ImportError:
    FILEWATCHING = False


class NoClientConfigured(Exception):
    def __init__(self):
        super(NoClientConfigured, self).__init__("Client ist nicht konfiguriert! Bitte Konfiguration abändern.")

class ClientConfig:
    def __init__(self, host: str, port: int, client_id: str, clean_session: bool, ca: str, cert: str, key:str, username: str, password: str, dpre: str):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.clean_session = clean_session
        self.ca = ca
        self.cert = cert
        self.key = key
        self.username = username
        self.password = password
        self.discorvery_prefix = dpre

    def is_secure(self) -> bool:
        return self.ca is not None and self.cert is not None and self.key is not None

    def broken_security(self) -> bool:
        return self.ca is not None or self.cert is not None or self.key is not None

    def has_user(self) -> bool:
        return self.username is not None and self.password is not None


class BasicConfig:

    def __init__(self, pfad: pathlib.Path, logger: logging.Logger, do_load=False, filesystem_listen=True):
        expanded = osp.expanduser(pfad)
        self._conf_path = pathlib.Path(expanded)
        self._logger = logger.getChild("BasicConfig")
        self._config = {}
        if do_load: self.load()
        if filesystem_listen and FILEWATCHING:
            self._register_watchdog()
        elif filesystem_listen and not FILEWATCHING:
            self._logger.warning(
                "Kann Dateiwächter nicht einrichten, nicht installiert. \n Bitte führe pip install watchdog aus.")
        else:
            self._logger.info("Automatisches neuladen der Konfiguration deaktiviert.")

    def load(self) -> None:
        try:
            resolved = str(self._conf_path.resolve())
            self._logger.debug("[1/2] Öffne Konfigurationsdatei zum laden " + resolved)
            self._config = None
            with open(resolved, "r") as json_file:
                self._config = json.load(json_file)
                self._logger.info("[2/2] Geladen...")
        except FileNotFoundError:
            self._logger.warning("[2/2] Nicht geladen. Datei existiert nicht.")
            self._config = {}
        if self._config.get("PLUGINS", None) is None:
            self._config["PLUGINS"] = {}

    def save(self) -> None:
        try:
            resolved = str(self._conf_path.resolve())
        except FileNotFoundError:
            resolved = str(self._conf_path.absolute())
        self._logger.debug("[1/2] Öffne Konfigurationsdatei zum speichern" + resolved)
        with open(resolved, "w") as json_file:
            json.dump(self._config, json_file, indent=2)
            self._logger.info("[2/2] Gespeichert...")

    def pre_reload(self):
        pass

    def post_reload(self):
        pass

    def _register_watchdog(self) -> None:
        pass

    def get_client_config(self) -> ClientConfig:

        if self._config.get("CLIENT", None) is None:
            self._config["CLIENT"] = {}
            self._config["CLIENT"]["host"] = "localhost"
            self._config["CLIENT"]["port"] = 1883
            self._config["CLIENT"]["client_id"] = None
            self._config["CLIENT"]["clean_session"] = True
            self._config["CLIENT"]["CA"] = None
            self._config["CLIENT"]["CERT"] = None
            self._config["CLIENT"]["KEY"] = None
            self._config["CLIENT"]["USER"] = None
            self._config["CLIENT"]["PW"] = None
            self._config["CLIENT"]["autodiscovery"] = None
            self.save()
            raise NoClientConfigured()

        client_config = self._config["CLIENT"]
        return ClientConfig(client_config["host"], client_config["port"],
                            client_config["client_id"], client_config["clean_session"], client_config["CA"],
                            client_config["CERT"], client_config["KEY"],
                            client_config["USER"], client_config["PW"], client_config["autodiscovery"])

    def get_all_plugin_names(self) -> set:
        plugins_config = self._config.get("PLUGINS", None)
        if plugins_config is None:
            self._config["PLUGINS"] = {}
            return set()
        return set(plugins_config.keys())

    def get_discovery_prefix(self):
        return self.get_client_config().discorvery_prefix

    def get_autodiscovery_topic(self, component: autodisc.Component, entitiy_id: str, dev_class: autodisc.DeviceClass, node_id=None) -> autodisc.Topics:
        cc = self.get_client_config()
        if node_id is None:
            return autodisc.getTopics(cc.discorvery_prefix, component,
                                  cc.client_id if cc.client_id is not None else cc.username, entitiy_id, dev_class)
        return autodisc.getTopics(cc.discorvery_prefix, component, node_id, entitiy_id, dev_class)

    def get_plugins_config(self, name) -> dict:
        if self._config.get("PLUGINS", {}).get(name, None) is None:
            self._config["PLUGINS"][name] = {}
        return self._config["PLUGINS"][name]

    def get(self, key: str, default=None):
        t = self[key]
        if t is None and default is not None:
            self[key] = default
        return self[key]

    def sett(self, key: str, value):
        self[key] = value

    def __getitem__(self, item: str):
        path = item.split("/")
        if len(path) == 1:
            return self._config.get("PLUGINS", {}).get(path[0], None)
        d = self.get_plugins_config(path[0])
        i = 1
        while True:
            if i < (len(path) - 1):
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if d.get(path[i], None) is None:
                    return None
                return d[path[i]]
            elif i > len(path):
                return d
            i += 1

    def __setitem__(self, key: str, value):
        path = key.split("/")
        if len(path) == 1:
            if value is None and path[0] in self._config["PLUGINS"].keys():
                del self._config["PLUGINS"][path[0]]
            elif value is not None:
                self._config["PLUGINS"][path[0]] = value
            return
        d = self.get_plugins_config(path[0])
        i = 1
        while True:
            if i < (len(path) - 1):
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if value is None:
                    try:
                        del d[path[i]]
                    except: pass
                else:
                    d[path[i]] = value
                break
            elif i > len(path):
                self._config["PLUGINS"] = value
                break
            i += 1

    def __delitem__(self, key:str):
        path = key.split("/")
        if len(path) == 1:
            return
        d = self.get_plugins_config(path[0])
        i = 1
        while True:
            if i < (len(path) - 1):
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if d.get(path[i], None) is None:
                    return
                del d[path[i]]
            elif i > len(path):
                del d
            i += 1

if FILEWATCHING:
    class FileWatchingConfig(watchevents.FileSystemEventHandler, BasicConfig):
        def load(self, reload=False):
            if reload:
                self._logger.info("Konfiguration wird neu geladen. Wurde verändert.")
                self.pre_reload()
                super().load()
                self.post_reload()
            else:
                super().load()

        def on_created(self, event: watchevents.DirCreatedEvent):
            if event.src_path == self._conf_path.absolute():
                self.load(True)

        def on_modified(self, event: watchevents.DirModifiedEvent):
            if event.src_path == self._conf_path.absolute():
                self.load(True)

        def on_moved(self, event: watchevents.DirMovedEvent):
            if event.dest_path == self._conf_path.absolute():
                self.load(True)

        def __init__(self, pfad: pathlib.Path, logger: logging.Logger, do_load=False, filesystem_listen=True):
            super().__init__(pfad, logger, do_load, filesystem_listen)

        def _register_watchdog(self):
            observer = Observer()
            observer.schedule(self, str(self._conf_path.parent), recursive=False)
            observer.start()


def config_factory(pfad: pathlib.Path, logger: logging.Logger, do_load=False, filesystem_listen=True) -> BasicConfig:
    if filesystem_listen and FILEWATCHING:
        return FileWatchingConfig(pfad, logger, do_load, filesystem_listen)
    else:
        return BasicConfig(pfad, logger, do_load, filesystem_listen)

if __name__ == '__main__':
    import pathlib

    log = logging.getLogger("Launch")
    log.setLevel(logging.DEBUG)
    # fh = logging.FileHandler('spam.log')
    # fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
    # fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    # logger.addHandler(fh)
    log.addHandler(ch)

    c = config_factory(pathlib.Path("/tmp/test.conf"), log, True)

    c.get("RaspberryPiGPIO", []).append({"test": "Hier ein test Text"})
    c["meh"] = None
    pass