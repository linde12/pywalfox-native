import logging
import sys
from pathlib import Path
from threading import Thread
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import ACTIONS, COMMANDS, DAEMON_VERSION
from .custom_css import (
    disable_custom_css,
    enable_custom_css,
    get_firefox_chrome_path,
    set_font_size,
)
from .fetcher import get_pywal_colors
from .messenger import Messenger
from .response import Message

if sys.platform.startswith("win32"):
    from .channel.win.server import Server
else:
    from .channel.unix.server import Server


class ColorChangeHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable):
        self.callback = callback

    def on_modified(self, event):
        print(f"event type: {event.event_type}  path : {event.src_path}")
        self.callback()


class Daemon:
    """
    Implements the daemon functionality that communicates with the extension.

    :param python_version str: the current major python version
    """

    def __init__(self, python_version):
        self.python_version = python_version
        self.set_chrome_path()
        self.messenger = Messenger(self.python_version)
        self.socket_server = Server()
        self.is_running = False
        self.observer = Observer()

    def set_chrome_path(self):
        """Tries to set the path to the chrome directory."""
        self.chrome_path = get_firefox_chrome_path()

    def check_chrome_path(self, action, target):
        """
        Checks if the path to the 'chrome' directory was found and sends a message if it was not.

        :param action str: the message action
        :param target str: the target CSS file
        :return: if chrome_path is set
        :rType: bool
        """
        if not self.chrome_path:
            self.messenger.send_message(
                Message(
                    action,
                    data=target,
                    success=False,
                    message="Could not find path to chrome folder",
                )
            )
            return False

        return True

    def check_target(self, message):
        """
        Checks if the message received specifies a target, or the message is invalid.

        :param message object: the decoded message
        :return: if message has key 'target' with a valid value
        :rType: bool
        """
        if "target" in message and len(message["target"]) > 0:
            return message["target"]

        logging.error("%s: target was not specified" % message["action"])
        self.send_invalid_action()
        return False

    def send_version(self):
        """Sends the current daemon version to the extension."""
        self.messenger.send_message(Message(ACTIONS["VERSION"], data=DAEMON_VERSION))

    def send_pywal_colors(self):
        """Sends the current colorscheme to the extension."""
        (success, pywal_data, message) = get_pywal_colors()
        self.messenger.send_message(
            Message(
                ACTIONS["COLORS"],
                data=pywal_data,
                success=success,
                message=message,
            )
        )

    def send_invalid_action(self):
        """Sends an action to the extension indicating that the action sent was invalid"""
        self.messenger.send_message(Message(ACTIONS["INVALID_ACTION"], success=False))

    def send_output(self, message):
        """
        Sends an output message to the extension that will be displayed in the 'Debugging output' area.

        :param message str: the message to send to the extension
        """
        self.messenger.send_message(Message(ACTIONS["OUTPUT"], data=message))

    def send_enable_css_response(self, message):
        """
        Tries to enable a custom CSS file and sends the result to the extension.

        :param message string: the name of the CSS file to enable/disable
        """
        action = ACTIONS["CSS_ENABLE"]
        target = self.check_target(message)
        if target is not False:
            if self.check_chrome_path(action, target):
                (success, message) = enable_custom_css(self.chrome_path, target)
                self.messenger.send_message(
                    Message(
                        action,
                        data=target,
                        success=success,
                        message=message,
                    )
                )

    def send_disable_css_response(self, message):
        """
        Tries to disable a custom CSS file and sends the result to the extension.

        :param message string: the name of the CSS file to enable/disable
        """
        action = ACTIONS["CSS_DISABLE"]
        target = self.check_target(message)
        if target is not False:
            if self.check_chrome_path(action, target):
                (success, message) = disable_custom_css(self.chrome_path, target)
                self.messenger.send_message(
                    Message(
                        action,
                        data=target,
                        success=success,
                        message=message,
                    )
                )

    def send_font_size_response(self, message):
        """
        Tries to set a custom font size in a CSS file.

        :param message string: the name of the CSS file to change the font size in
        """
        action = ACTIONS["CSS_FONT_SIZE"]
        target = self.check_target(message)
        if target is not False:
            if self.check_chrome_path(action, target):
                if "size" in message:
                    new_size = message["size"]
                    (success, message) = set_font_size(
                        self.chrome_path, target, new_size
                    )
                    self.messenger.send_message(
                        Message(
                            action,
                            data=new_size,
                            success=success,
                            message=message,
                        )
                    )

    def send_theme_mode(self, mode):
        """
        Sends the new theme mode to be activated.

        :param mode string: the new theme mode (dark/light)
        """
        self.messenger.send_message(
            Message(
                ACTIONS["THEME_MODE"],
                data=mode,
            )
        )

    def handle_message(self, message):
        """
        Handles the incoming messages and does the appropriate action.

        :param message object: the decoded message
        """
        try:
            action = message["action"]
            if action == ACTIONS["VERSION"]:
                self.send_version()
            elif action == ACTIONS["COLORS"]:
                self.send_pywal_colors()
            elif action == ACTIONS["CSS_ENABLE"]:
                self.send_enable_css_response(message)
            elif action == ACTIONS["CSS_DISABLE"]:
                self.send_disable_css_response(message)
            elif action == ACTIONS["CSS_FONT_SIZE"]:
                self.send_font_size_response(message)
            else:
                logging.debug("%s: no such action" % action)
                self.send_invalid_action()
        except KeyError:
            logging.error("action was not defined")
            self.send_invalid_action()

    def socket_thread_worker(self):
        """The socket server thread worker."""
        while True:
            message = self.socket_server.get_message()
            if message == COMMANDS["UPDATE"]:
                logging.debug("CLI: Update pywal colors")
                self.send_pywal_colors()
            elif message == COMMANDS["THEME_MODE_DARK"]:
                logging.debug("CLI: Set theme mode to dark")
                self.send_theme_mode("dark")
            elif message == COMMANDS["THEME_MODE_LIGHT"]:
                logging.debug("CLI: Set theme mode to light")
                self.send_theme_mode("light")
            elif message == COMMANDS["THEME_MODE_AUTO"]:
                logging.debug("CLI: Set theme mode to auto")
                self.send_theme_mode("auto")

    def start_socket_server(self):
        """Starts the socket server and creates the socket thread."""
        success = self.socket_server.start()
        if success is True:
            if self.python_version == 3:
                self.socket_thread = Thread(
                    target=self.socket_thread_worker, daemon=True
                )
            else:
                self.socket_thread = Thread(target=self.socket_thread_worker)
                self.socket_thread.daemon = True

            self.socket_thread.start()

    def start(self):
        """Starts the daemon and listens for incoming messages."""
        self.is_running = True
        self.start_socket_server()

        # start observing pywal colors file and send them to ff whenever it changes
        self.observer.schedule(
            event_handler=ColorChangeHandler(self.send_pywal_colors),
            path=str(Path.home() / ".cache" / "wal" / "colors"),
            recursive=False,
        )
        self.observer.start()

        while self.is_running:
            message = self.messenger.get_message()
            logging.debug("Received message from extension: %s" % message)
            self.handle_message(message)

    def close(self):
        """Application cleanup."""
        logging.debug("Running cleanup")
        self.is_running = False
        self.socket_server.close()
        self.observer.stop()
        sys.exit(0)
