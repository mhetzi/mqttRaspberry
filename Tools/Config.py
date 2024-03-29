# -*- coding: utf-8 -*-
from abc import abstractmethod
from numbers import Number
import pathlib
import os.path as osp
from pathlib import Path
import logging
import Tools.Autodiscovery as autodisc
import Tools.ResettableTimer as rtimer
import time

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
    try:
        import Tools.error as err
        err.try_install_package('watchdog')
    except err.RestartError:
        from watchdog.observers import Observer
        import watchdog.events as watchevents
        FILEWATCHING = True
    except:
        FILEWATCHING = False
from typing import Dict, Tuple, Sequence, Union


class DictBrowser:
    def __init__(self, backing_dict: dict, logger: logging.Logger = None) -> None:
        self._dict = backing_dict
        #self._log = logger if logger is not None else logging.getLogger("Launch.DictBrowser")
    
    def get(self, key: str, default=None):
        t = self[key]
        if t is None and default is not None:
            self[key] = default
        return self[key]

    def sett(self, key: str, value):
        self[key] = value

    def __getitem__(self, item: str) -> Union[dict, list, int, float, bool, str, None]:
        path = item.split("/")
        d: Union[dict, list] = self._dict
        i = 0
        while True:
            if i < (len(path) - 1):
                if isinstance(d, list):
                    int_path = int(path[i])
                    d = d[int_path]
                    i += 1
                    continue
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if isinstance(d, list):
                    int_path = int(path[i])
                    if int_path > len(d) - 1:
                        return None
                    return d[int_path]
                if d.get(path[i], None) is None:
                    return None
                return d[path[i]]
            elif i > len(path):
                return d
            i += 1

    def __setitem__(self, key: str, value):
        path = key.split("/")
        d: Union[dict, list] = self._dict
        i = 0
        while True:
            if i < (len(path) - 1):
                if isinstance(d, list):
                    int_path = int(path[i])
                    d = d[int_path]
                    i += 1
                    continue
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if isinstance(d, list):
                    int_path = int(path[i])
                    if value is None:
                        try:
                            d.pop(int_path)
                        except:pass
                    d[int_path] = value
                    break
                if value is None:
                    try:
                        del d[path[i]]
                    except: pass
                else:
                    d[path[i]] = value
                break
            elif i > len(path):
                break
            i += 1

    def __delitem__(self, key:str):
        path = key.split("/")
        d: Union[dict, list] = self._dict
        i = 0
        while True:
            if i < (len(path) - 1):
                if d.get(path[i], None) is None:
                    d[path[i]] = {}
                d = d[path[i]]
            elif i == (len(path) - 1):
                if isinstance(d, list):
                    d.pop(int(path[i]))
                    return
                if d.get(path[i], None) is None:
                    return
                del d[path[i]]
            elif i > len(path):
                del d
            i += 1
    
    def listDeep(self, d=None, prepand="/") -> list:
        d = d if d is not None else self._dict
        ls = []
        for key, value in d.items():
            if isinstance(value, dict):
                ls.append(self.listDeep(value, "{}/{}/".format(prepand, key)))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        ls.append(self.listDeep(value, "{}/{}/".format(prepand, key)))
            else:
                ls.append("{}/{}".format(prepand, key), value)
        return ls

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
        self.id = client_id if client_id != "" else username
        self.isOnlineTopic = "online/{}".format(self.id)


    def is_secure(self) -> bool:
        print("is_secure(): ca: {}, cert: {}, key: {}, port: {}".format(self.ca, self.cert, self.key, self.port))
        return self.ca is not None and self.cert is not None and self.key is not None and self.port != 1883

    def broken_security(self) -> bool:
        return self.ca is not None or self.cert is not None or self.key is not None

    def has_user(self) -> bool:
        return self.username is not None and self.password is not None

class AbstractConfig:
    @abstractmethod
    def load(self, fileNotFoundOK=True):
        pass

    @abstractmethod
    def am_i_saving(self) -> bool:
        pass

    @abstractmethod
    def save(self, delayed=False) -> None:
        pass

    @abstractmethod
    def get_autodiscovery_topic(self, component: autodisc.Component, entitiy_id: str, dev_class: autodisc.DeviceClass, node_id=None, ownOfflineTopic=False) -> autodisc.Topics:
        pass

    @abstractmethod
    def getIndependendFile(self, name:str, no_watchdog=False, do_load=True):
        pass

    @abstractmethod
    def getIndependendPath(self, name:str) -> Path:
        pass

    @abstractmethod
    def __getitem__(self, item: str) -> Union[dict, int, str, list]:
        pass

    @abstractmethod
    def __setitem__(self, key: str, value):
        pass

    @abstractmethod
    def __delitem__(self, key:str):
        pass

    @abstractmethod
    def markFileAsDirty(self):
        pass

class BasicConfig(AbstractConfig):
    _is_in_saving = False
    _dict_browser: DictBrowser = None

    def __init__(self, pfad: Path, logger: logging.Logger, do_load=False, filesystem_listen=True):
        self._conf_path = pfad.expanduser()
        self._logger = logger.getChild("BasicConfig")
        self._config = {}
        if do_load: self.load(fileNotFoundOK=True)
        if filesystem_listen and FILEWATCHING:
            self._register_watchdog()
        elif filesystem_listen and not FILEWATCHING:
            self._logger.warning(
                "Kann Dateiwächter nicht einrichten, nicht installiert. \n Bitte führe pip install watchdog aus.")
        else:
            self._logger.info("Automatisches neuladen der Konfiguration deaktiviert.")
        
        self.autoSave = rtimer.ResettableTimer(30,function=self.save, userval=None, autorun=False)
        self.file_is_dirty = False

    def load(self, fileNotFoundOK=True) -> None:
        try:
            self._logger.info("[1/2] Öffne Konfigurationsdatei zum laden " + str(self._conf_path.absolute()))
            self._config = None
            with self._conf_path.open("r") as json_file:
                self._config = json.load(json_file)
                self._logger.info("[2/2] Geladen...")
        except Exception:
            self._logger.exception("Fehler beim Laden von Config")
            self._logger.warning("[2/2] Nicht geladen. Datei existiert nicht.")
            try:
                backup = self._conf_path.with_suffix(".cbackup")
                self._logger.info("[3/4] Öffne Backup Konfigurationsdatei zum laden " + str(backup.absolute()))
                self._config = None
                with backup.open("r") as json_file:
                    self._config = json.load(json_file)
                    self._logger.info("[4/4] Geladen...")
            except FileNotFoundError as e:
                if not fileNotFoundOK:
                    raise e
                else:
                    self._logger.error("[4/4] Backup konne ebenfalls nicht geladen werden!")
                    self._config = {}
            except Exception:
                self._logger.error("[4/4] Backup konne ebenfalls nicht geladen werden!")
                self._config = {}

        if self._config.get("PLUGINS", None) is None:
            self._config["PLUGINS"] = {}
        
        self._dict_browser = DictBrowser(self._config, self._logger.getChild("DictBrowser"))
        

    def am_i_saving(self) -> bool:
        return self._is_in_saving

    def save(self, delayed=False) -> None:
        if delayed:
            self.autoSave.reset()
            return
        if self.autoSave is not None:
            self.autoSave.cancel()
        if not self.file_is_dirty:
            return
        self._is_in_saving = True
        self._logger.debug("[1/3] Erstelle Backup der alten Konfig...")
        if self._conf_path.exists():
            try:
                self._conf_path.with_suffix(".cbackup").unlink()
            except FileNotFoundError:
                pass
            self._conf_path.rename(self._conf_path.with_suffix(".cbackup"))
        self._logger.debug("[2/3] Öffne Konfigurationsdatei zum speichern " + str(self._conf_path.absolute()))
        with self._conf_path.open("w") as json_file:
            json.dump(self._config, json_file, indent=2)
            self._logger.info("[3/3] Gespeichert...")
            self.file_is_dirty = False
        time.sleep(2)
        self._is_in_saving = False

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
            self.file_is_dirty = True
            self.save(delayed=False)
            raise NoClientConfigured()

        client_config = self._config["CLIENT"]

        import platform
        plat = platform.system()

        return ClientConfig(client_config["host"], client_config["port"],
                            client_config["client_id"].format(os=plat), client_config["clean_session"], client_config["CA"],
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

    def get_autodiscovery_topic(self, component: autodisc.Component, entitiy_id: str, dev_class: autodisc.DeviceClass, node_id=None, ownOfflineTopic=False, subnode_id=None) -> autodisc.Topics:
        cc = self.get_client_config()
        topics = None
        if node_id is None:
            nid = entitiy_id
            if subnode_id is not None:
                nid = "{}_{}".format(subnode_id, entitiy_id)
            topics = autodisc.getTopics(cc.discorvery_prefix, component, cc.client_id if cc.client_id is not None else cc.username, 
                nid, dev_class)
        else:
            topics = autodisc.getTopics(cc.discorvery_prefix, component, node_id, entitiy_id, dev_class)
        if not ownOfflineTopic:
            topics.ava_topic = cc.isOnlineTopic
        return topics

    def get_plugins_config(self, name) -> dict:
        if self._config.get("PLUGINS", {}).get(name, None) is None:
            self._config["PLUGINS"][name] = {}
        return self._config["PLUGINS"][name]
    
    def getIndependendFile(self, name:str, no_watchdog=False, do_load=True):
        new_path = self.getIndependendPath(name=name)
        c = config_factory(pfad=new_path, logger=self._logger, do_load=do_load, filesystem_listen=not no_watchdog)
        return (c, name)

    def getIndependendPath(self, name:str) -> Path:
        if name is None:
            self._logger.info("Kein Name angegeben.")
            import uuid
            uid = uuid.uuid4()
            name = str(uid)
            self._logger.info("Name {} wurde generiert.".format(name))
        self._logger.debug("Generiere Configpath von {} + {}".format(self._conf_path.parent, "{}.config".format(name)))
        return self._conf_path.parent.joinpath("{}.config".format(name))

    def stop(self):
        pass

    def get(self, key: str, default=None):
        key = "PLUGINS/{}".format(key)
        return self._dict_browser.get(key, default=default)

    def sett(self, key: str, value):
        key = "PLUGINS/{}".format(key)
        self._dict_browser[key] = value
        self.save(delayed=True)

    def __getitem__(self, key: str):
        key = "PLUGINS/{}".format(key)
        return self._dict_browser[key]

    def __setitem__(self, key: str, value):
        key = "PLUGINS/{}".format(key)
        self._dict_browser[key] = value
        self.file_is_dirty = True
        self.save(True)

    def __delitem__(self, key:str):
        key = "PLUGINS/{}".format(key)
        del self._dict_browser[key]
        
    def markFileAsDirty(self):
        self.file_is_dirty = True
        self.save(True)


if FILEWATCHING:
    class FileWatchingConfig(watchevents.FileSystemEventHandler, BasicConfig):
        def load(self, reload=False, fileNotFoundOK=True):
            if self._is_in_saving:
                return
            if reload:
                self._logger.info("Konfiguration wird neu geladen. Wurde verändert.")
                self.pre_reload()
                super().load(fileNotFoundOK=fileNotFoundOK)
                self.post_reload()
            else:
                super().load(fileNotFoundOK=fileNotFoundOK)

        def on_modified(self, event: watchevents.DirModifiedEvent):
            try:
                if self._conf_path.samefile(event.src_path):
                    self.load(reload=True, fileNotFoundOK=False)
            except: pass

        def on_moved(self, event: watchevents.DirMovedEvent):
            try:
                if self._conf_path.samefile(event.src_path):
                    self.load(reload=True, fileNotFoundOK=True)
            except: pass

        def __init__(self, pfad: pathlib.Path, logger: logging.Logger, do_load=False, filesystem_listen=True):
            super().__init__(pfad, logger, do_load, filesystem_listen)
            self._observer = None

        def __del__(self):
            self.stop()

        def stop(self):
            try:
                self._observer.stop()
                print("Observer killed")
            except:
                pass
            
        def _register_watchdog(self):
            try:
                self._observer = Observer()
                self._observer.name = "ConfigWatchdog"
                self._observer.schedule(self, str(self._conf_path.parent), recursive=False)
                self._observer.start()
            except OSError:
                pass

class PluginConfig(AbstractConfig):

    def __init__(self, config: AbstractConfig, plugin_name:str):
        self._main  = config
        self._pname = plugin_name
        self.get_autodiscovery_topic = self._main.get_autodiscovery_topic
        self.getIndependendFile      = self._main.getIndependendFile
        self.getIndependendPath      = self._main.getIndependendPath

    def save(self):
        self._main.save()

    def get(self, key: str, default=None):
        t = self[key]
        if t is None and default is not None:
            self[key] = default
        return self[key]

    def sett(self, key: str, value):
        key = "{}/{}".format(self._pname, key)
        self._main[key] = value

    def __getitem__(self, item: str):
        key = "{}/{}".format(self._pname, item)
        return self._main[key]

    def __setitem__(self, key: str, value):
        key = "{}/{}".format(self._pname, key)
        self._main[key] = value

    def __delitem__(self, key:str):
        key = "{}/{}".format(self._pname, key)
        del self._main[key]
        
    def markFileAsDirty(self):
        self._main.markFileAsDirty()
    

def config_factory(pfad: pathlib.Path, logger: logging.Logger, do_load=False, filesystem_listen=True) -> BasicConfig:
    if isinstance(pfad, str):
        pfad = Path(pfad)
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