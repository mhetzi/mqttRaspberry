#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import getopt
import ssl
import sys
import logging
import threading
import time
from typing import Any, Coroutine

from textual.message import Message
import Tools.PluginManager as pman
import Tools.Config as tc
import signal
import ctypes
import datetime
from pathlib import Path
import faulthandler
import dataclasses

LIB = 'libcap.so.2'
try:
    libcap = ctypes.CDLL(LIB)
except OSError:
    print(
        'Library {} not found. Unable to set thread name.'.format(LIB)
    )
else:
    def _name_hack(self):
        # PR_SET_NAME = 15
        libcap.prctl(15, self.name.encode())
        threading.Thread._bootstrap_original(self)

    threading.Thread._bootstrap_original = threading.Thread._bootstrap
    threading.Thread._bootstrap = _name_hack

import Tools.PropagetingThread as propt
propt.installProagetingThread()

try:
    import setproctitle
except ImportError as ie:
    from Tools import error as err
    try:
        err.try_install_package('setproctitle', throw=ie, ask=False)
    except err.RestartError:
        try:
            import setproctitle
        except:
            pass
    except:
        pass

try:
    import textual
except ImportError as ie:
    from Tools import error as err
    try:
        err.try_install_package('textual', throw=ie, ask=False)
    except err.RestartError:
        try:
            import setproctitle
        except:
            pass

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Tabs, Tab, Button, TabbedContent, TabPane, OptionList, Footer, RichLog, Label
from textual.widgets.option_list import Option, Separator
from textual.binding import Binding
from threading import Timer

class TextHandler(logging.Handler):
    """Class for  logging to a TextLog widget"""

    def __init__(self, textlog: RichLog):
        # run the regular Handler __init__
        logging.Handler.__init__(self)
        # Store a reference to the Text it will log to
        self.text = textlog

    def emit(self, record):
        msg = self.format(record)
        style = "gray"
        match record.levelno:
            case 10: style = "blue"
            case 20: style = "white"
            case 30: style = "yellow"
            case 40: style = "red"
            case 50: style = "red"
        # style your output depending on e.g record.levelno here
        self.text.write(f"[bold {style}]{msg}")

class PluginInstallButton(Button):
    _module_list: list[str] = []
    _plugin_list = None
    _current_option = None

    def _press_threaded(self):
        self.app._master_logger.info("Beginn Install via pip")
        from Tools import error
        for i in self._module_list:
            try:
                self.app._master_logger.info(f"PIP: Installing {i}...")
                error.try_install_package(i, throw=ImportError("Install failed!"), ask=False)
            except error.RestartError:
                self.app._master_logger.info(f"PIP: Install {i}. OK.")
        try:
            self._plugin_list.on_option_list_option_selected(self._current_option)
        except:
            self.app._master_logger.exception("Configure Reload failed!")
    
    def press(self):
        thr = threading.Thread(name="Pip installer", daemon=True, target=self._press_threaded)
        thr.start()
        return super().press()

class PluginOption(Option):
    _plugin:pman.PluginLoader|None = None

class PluginList(OptionList):
    _timer = None
    _log: logging.Logger = None

    def reload_list(self):
        self.app.reload_configs()
        self.set_lists(self.app._all_configs, self.app._enabled_configs)
        self.app.query_one("#main_tabbed_content").active = "plugin_pane"

    def set_app(self, app, log):
        self._timer = Timer(2.0, self.reload_list)
        self._timer.start()
        self._log = log

    def set_lists(self, all:list[pman.PluginLoader], enabled:list[pman.PluginLoader]):
        self.clear_options()
        
        enabled_str = [x.getConfigKey() for x in enabled]
        added = []

        for i in all:
            en = i.getConfigKey() in enabled_str
            if i.getConfigKey() not in added:
                op = PluginOption(f"[bold {'green' if en else 'red'}]{i.getConfigKey()}", i.getConfigKey())
                op._plugin = i
                self.add_option(
                    op
                )
            added.append(i.getConfigKey())
        self._log.info("Plugin List reloaded!")
    
    def on_option_list_option_selected(self, msg: OptionList.OptionSelected|PluginOption):
        opt: PluginOption = msg if isinstance(msg, PluginOption) else msg.option
        self.app.query_one("#main_tabbed_content").active = "cfg_plugin_tab"

        self._log.debug(f"Selected Option {opt.prompt}")
        tab: TabPane = self.app.query_one("#cfg_plugin_editor_label")
        
        tab.remove_children()

        l = opt._plugin.getNeededPipModules()
        
        if len(l) > 0:
            tab.mount(Label(f"Plugin {opt._plugin.getConfigKey()} PiP installer."))
            tab.mount(Label((f"  The Plugin Requests these PIP installs:")))
            for i in l:
                tab.mount(Label(f"      {i}"))
            btn = PluginInstallButton("Install", name="pip_do_install", id="do_pip_install")
            btn._module_list = l
            btn._plugin_list = self
            btn._current_option = opt
            tab.mount(btn)
        else:
            tab.mount(Label(f"Configure {opt._plugin.getConfigKey()}:"))            

class ConfigureApp(App):
    BINDINGS = [
        Binding(key="q", action="quit", description="Quit"),
        Binding(key="s", action="save", description="Save"),
        Binding(key="r", action="plugins_reload", description="Reload"),
    ]

    _ml = None

    def __init__(self):
        super().__init__()


        log = logging.getLogger("Configure")
        log.setLevel(logging.DEBUG)
        # fh = logging.FileHandler('spam.log')
        # fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = TextualHandler()
        ch.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
        # fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        log.addHandler(ch)
        self._master_logger = log

        prog_args = sys.argv[1:]
        t_args = prog_args.copy()

        configPath = "~/.config/mqttra.config"

        while True:
            try:
                opts, args = getopt.gnu_getopt(t_args, "h?c:",
                                               ["help", "config=",])
                break
            except getopt.error as e:
                opt = e.msg.replace("option ", "").replace(" not recognized", "")
                t_args.remove(opt)

        for opt, arg in opts:
            if opt == "-c" or opt == "--config":
                configPath = arg
            elif opt == "-?" or opt == "-h" or opt == "help":
                self._master_logger.info("""
                                        ============ HILFE ============
                    -c --config             Konfigurations Datei angeben (Standartpfad ~/.config/mqttra.config)
                    -? -h --help            Diese Nachricht anzeigen
                """)
                return

        self.configPath = Path(configPath)

        self._enabled_configs = []
        self._all_configs = []
        self._disabled_configs = []

    def reload_configs(self):
        self._master_logger.info("Build PluginManager environment...")
        config = tc.config_factory(self.configPath, logger=self._master_logger, do_load=True, filesystem_listen=False)
        from Tools import _std_dev_info
        import Tools.Autodiscovery as ad
        devInfo = _std_dev_info.DevInfoFactory.build_std_device_info(self._master_logger.getChild("std_dev"))
        ad.Topics.set_standard_deviceinfo(devInfo)

        try:
            import Tools.error as err
            err.set_system_mode(True)
        except:
            pass

        self.pm = pman.PluginManager(self._master_logger, config)

        self._master_logger.info("Getting enabled Plugins...")
        self._enabled_configs = self.pm.needed_plugins(False)
        self._master_logger.info("Get all Plugins...")
        self._all_configs = self.pm.needed_plugins(True)
        self._disabled_configs = [item for item in self._all_configs if item not in self._enabled_configs]


    def compose(self) -> ComposeResult:
        with TabbedContent(id="main_tabbed_content"):
            with TabPane("Log", id="master_log_pane"):
                yield RichLog(highlight=True, name="Logger", id="master_log", markup=True)
            with TabPane("Plugins", id="plugin_pane"):
                ml = PluginList(name="PluginList", id="plugin_list")
                ml.set_app(self, self._master_logger)
                self._ml = ml
                yield ml
            with TabPane("Configure", name="configure_plugin", id="cfg_plugin_tab"):
                yield Label("Plugin Configuration Editor", id="cfg_plugin_editor_label")
        yield Footer()

    def on_ready(self):
        text_log: RichLog = self.query_one("#master_log")

        logger = self._master_logger
        logger.setLevel(logging.DEBUG)
        th = TextHandler(text_log)
        th.setLevel(logging.DEBUG)
        logger.addHandler(th)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
        th.setFormatter(formatter)

    def action_plugins_reload(self):
        self._ml.reload_list()


if __name__ == "__main__":
    app = ConfigureApp()
    app.run()