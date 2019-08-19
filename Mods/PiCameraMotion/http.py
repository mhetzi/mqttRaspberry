# -*- coding: utf-8 -*-

import io
import picamera
import logging
import socketserver
from threading import Condition
from http import server
import urllib
import threading
import time

try:
    import json as json
except ImportError:
    import simplejson as json

PAGE = """\
<html>
<head>
<title>PiCamera Plugin</title>
</head>
<body>
<h1>mqtt PiCamera Plugin</h1>
<p>
<a href="calibrate.run">Minimalen Block Noise ermitteln</a>
<a href="stream.mjpg">Stream in Vollbild</a>
<a href="snap.jpg">Snapshot erstellen</a>
<a href="info.json">Debug JSON abrufen</a>
<a href="settings.html">Einstellungen</a>
<p>
<img src="stream.mjpg" width="640" height="480" />
<p>
<object data="info.json" />
</body>
</html>
"""

SETTINGS = u"""<html><head><title>PiCamera Plugin Settings</title></head><body><h1>mqtt PiCamera Plugin Settings</h1><p>
<form action="/updateMotion.data" method="get">  Ueber Blockanzahl
<input type="number" name="maxCount" value="{}"> ignorieren<br>  Minimale Blockanzahl
<input type="number" name="minCount" value="{}"><br>  Minimaler Veränderungswert
<input type="number" name="minBlock" value="{}"><br>Bilder bis zur Bewegungserkennung
<input type="number" name="mF" value="{}"><br>  Bilder ohne Bewegung
<input type="number" name="sF" value="{}"><br>  Bilder  Bewegung
<input type="number" name="shutter" value="{}"><br> Shutterspeed
<input type="number" name="exposure ReadOnly" value="{}"><br> exposure
<input type="" name="exposure_mode" value="{}"><br> exposure_mode
<input type="number" name="color_effects_u" value="{}"><br> color_effect_u
<input type="number" name="color_effects_v" value="{}"><br> color_effect_v
<input type="number" name="iso" value="{}"><br> ISO
<input type="submit" value="Übernehmen"></form>"""


class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class StreamingJsonOutput(object):
    def __init__(self):
        self.data = b''
        self.condition = Condition()

    def write(self, buf: dict):
        if buf is not None:
            # New json, copy the existing buffer's content and notify all
            # clients it's available
            with self.condition:
                self.json = json.dumps(buf).encode('utf-8')
                self.condition.notify_all()
        return len(buf)


class StreamingPictureOutput(object):

    requested = False

    def talkback(self):
        raise NotImplementedError()

    def do_talkback(self, force=False):
        if not self.requested or force:
            print("do_talkback({}): wasRequested: {}".format(
                force, self.requested))
            self.requested = True
            self.talkback()

    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        return self.buffer.write(buf)

    def flush(self):
        self.buffer.truncate()
        with self.condition:
            self.frame = self.buffer.getvalue()
            self.condition.notify_all()
            self.requested = False
        self.buffer.seek(0)


def makeStreamingHandler(output: StreamingOutput, json: StreamingJsonOutput):
    class StreamingHandler(server.BaseHTTPRequestHandler):
        def meassure_call(self):
            logging.warning("meassure_call nicht überladen")

        def fill_setting_html(self, html: str):
            logging.warning("fill_setting_html nicht überladen")
            return html

        def update_settings_call(self, countMaxNoise, countMinNoise, blockMaxNoise, frameToTriggerMotion, framesToNoMotion):
            logging.warning("update_settings_call nicht überladen")

        def do_GET(self):
            if self.path == '/':
                self.send_response(301)
                self.send_header('Location', '/index.html')
                self.end_headers()
            elif self.path == '/index.html':
                content = PAGE.encode('utf-8')
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            elif self.path == '/stream.mjpg':
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Cache-Control', 'no-cache, private')
                self.send_header('Pragma', 'no-cache')
                self.send_header(
                    'Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
                self.end_headers()
                try:
                    while True:
                        with output.condition:
                            output.condition.wait()
                            frame = output.frame
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                except Exception as e:
                    logging.warning(
                        'HTTP Client %s entfernt: %s',
                        self.client_address, str(e))
            elif self.path == '/snap.jpg':
                try:
                    frame = None
                    with output.condition:
                        frame = output.frame
                    self.send_response(200)
                    self.send_header('Age', 0)
                    self.send_header('Cache-Control', 'no-cache, private')
                    self.send_header('Pragma', 'no-cache')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
                except Exception as e:
                    logging.warning(
                        'HTTP Client %s entfernt: %s',
                        self.client_address, str(e))
            elif self.path == "/info.json":
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Cache-Control', 'no-cache, private')
                self.send_header('Pragma', 'no-cache')
                self.send_header(
                    'Content-Type', 'multipart/x-mixed-replace; boundary=NEW_JSON_DATA')
                self.end_headers()
                try:
                    while True:
                        with json.condition:
                            json.condition.wait()
                            js = json.json
                        self.wfile.write(b'--NEW_JSON_DATA\r\n')
                        self.send_header('Content-Type', 'text/json')
                        self.send_header('Content-Length', len(js))
                        self.end_headers()
                        self.wfile.write(js)
                        self.wfile.write(b'\r\n')
                except Exception as e:
                    logging.warning(
                        'HTTP Client %s entfernt: %s',
                        self.client_address, str(e))
            elif self.path == "/calibrate.run":
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Cache-Control', 'no-cache, private')
                self.send_header('Pragma', 'no-cache')
                self.send_header(
                    'Content-Type', 'multipart/x-mixed-replace; boundary=NEW_JSON_DATA')
                self.end_headers()
                self.wfile.write(b'OK!')
                self.wfile.write(b'\r\n')
                if self.meassure_call is not None:
                    self.meassure_call()
            elif self.path.startswith("/updateMotion.data"):
                data = self.path.replace("/updateMotion.data?", "")
                data = urllib.parse.parse_qs(data)
                if len(data) < 1:
                    self.send_response(500, "Keine Parameter!")
                    return
                
                self.send_response(200)
                print("Habe von Client {} bekommen.".format(data))
                # {'mF': ['2'], 'minBlock': ['2500'], 'minCount': ['3'], 'maxCount': ['6000'], 'sF': ['300']}
                self.update_settings_call(
                    int(data.get("maxCount", [None])[0]),
                    int(data.get("minCount", [None])[0]),
                    int(data.get("minBlock", [None])[0]),
                    int(data.get("mF"      , [None])[0]),
                    int(data.get("sF"      , [None])[0])
                )
                content = u"<html><head><title>PiCamera Plugin</title></head><body><h1><OK Einstellungen gespeichert</h1><p>In Kürze wird die die Hauptseite geladen...<p><meta http-equiv="refresh" content="3;url=/index.html" /><p></body></html>"
                content = content.encode('utf-8')
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            elif self.path == "/settings.html":
                print("Generiere SETTINGS:")
                content = self.fill_setting_html(SETTINGS)
                content = content.encode('utf-8')
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
                self.end_headers()
    return StreamingHandler


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = False
    logger = None

    def run(self):
        self.serve_forever()
        self.logger.info("Server beendet")

    def stop(self):
        self.logger.info("Server wird beendet")
        self.shutdown()
