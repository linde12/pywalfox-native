import sys
import logging
from threading import Thread

import config
import fetcher
import custom_css

from response import Message
from messenger import Messenger
from channel.server as Server

class Daemon:
    """
    Application entry point. Initializes the application.

    :param debug bool: if debugging is enabled (defaults to True)
    """
    def __init__(self, debug=False):
        self.debug = debug
        self.set_logging()
        self.set_chrome_path()
        self.set_actions()
        self.messenger = Messenger()
        self.socket_server = Server(config.SOCKET_PATH)

    def set_actions(self):
        """Defines the different messages from the addon that will be handled."""
        self.actions = {}
        self.actions[config.ACTIONS['version']] = self.send_version
        self.actions[config.ACTIONS['colors']] = self.send_colorscheme
        self.actions[config.ACTIONS['custom_css_enable']] = self.send_enable_css_response
        self.actions[config.ACTIONS['custom_css_disable']] = self.send_disable_css_response

    def set_chrome_path(self):
        """Tries to set the path to the chrome directory."""
        self.chrome_path = custom_css.get_firefox_chrome_path()
        if not self.chrome_path:
            logging.error('Could not find Firefox profile directory')
        else:
            logging.debug('Found valid chrome directory path')

    def set_logging(self):
        """Setup logging format and destination."""
        log_level = logging.ERROR
        if self.debug == True:
            log_level = logging.DEBUG

        logging.basicConfig(
            format='[%(asctime)s] %(levelname)s:%(message)s',
            datefmt='%m/%d/%Y %I:%M:%S %p',
            filename=LOG_FILE,
            level=log_level
        )

    def check_chrome_path(self, action):
        """
        Checks if the path to the 'chrome' directory was found and sends a message if it was not.

        :return: if chrome_path is set
        :rType: bool
        """
        if not self.chrome_path:
            this.messenger.send_message(Message(
                config.ACTIONS['custom_css_apply'],
                'Could not find path to chrome folder',
                success=False
            ))
            return False
        else:
            return True

    def check_target(self, message):
        """
        Checks if the message received specifies a target, or the message is invalid.

        :param message object: the decoded message
        :return: if message has key 'target' with a valid value
        :rType: bool
        """
        if 'target' in message and len(message['target']) > 0:
            return message['target']

        this.messenger.send_invalid_action()
        return False

    def send_version(self, message):
        """Sends the current daemon version to the addon."""
        self.messenger.send_message(Message(config.ACTIONS['version'], config.DAEMON_VERSION))

    def send_colorscheme(self, message):
        """Sends the current colorscheme to the addon."""
        (success, data) = fetcher.get_colorscheme(config.PYWAL_COLORS_PATH, config.BG_LIGHT_MODIFIER)
        if success == True:
            logging.debug('Successfully fetched pywal colors')
        else:
            logging.error(data)

        this.messenger.send_message(Message(config.ACTIONS['colors'], data, success=success))

    def send_invalid_action(self):
        """Sends an action to the addon indicating that the action sent was invalid"""
        this.messenger.send_message(Message(config.ACTIONS['invalid_action'], {}, success=False))

    def send_output(self, message):
        """
        Sends an output message to the addon that will be displayed in the 'Debugging output' area.

        :param message str: the message to send to the addon
        """
        this.messenger.send_message(Message(config.ACTIONS['output'], message))

    def send_enable_css_response(self, message):
        """
        Tries to enable a custom CSS file and sends the result to the addon.

        :param target string: the name of the CSS file to enable/disable
        """
        action = config.ACTIONS['custom_css_enable']
        target = self.check_target(message)
        if target is not False:
            if self.check_chrome_path(action):
                (success, message) = custom_css.enable_custom_css(self.chrome_path, target)
                this.messenger.send_message(Message(action, message, success=success))

    def send_disable_css_response(self, message):
        """
        Tries to disable a custom CSS file and sends the result to the addon.

        :param target string: the name of the CSS file to enable/disable
        """
        action = config.ACTIONS['custom_css_disable']
        target = self.check_target(message)
        if target is not False:
            if self.check_chrome_path(action):
                (success, message) = custom_css.disable_custom_css(self.chrome_path, target)
                this.messenger.send_message(Message(action, message, success=success))

    def handle_message(self, message):
        """
        Handles the incoming messages and does the appropriate action.

        :param message object: the decoded message
        """
        try:
            action = message['action']
            if action in self.actions:
                self.actions[action](message)
            else:
                self.send_invalid_action()
        except KeyError:
            self.send_invalid_action()

    def socket_thread_worker(self):
        """The socket server thread worker."""
        while True:
            message = self.socket_server.get_message()
            if message == 'update':
                self.send_colorscheme()

    def start_socket_server(self):
        """Starts the socket server and creates the socket thread."""
        success = self.socket_server.start()
        if success == True:
            # We use daemon=True so that the thread will exit when the daemon exits.
            # https://docs.python.org/2/library/threading.html#threading.Thread.daemon
            self.socket_thread = Thread(target=self.socket_thread_worker, daemon=True)
            self.socket_thread.start()

    def start(self):
        """Starts the daemon and listens for incoming messages."""
        self.start_socket_server()
        while True:
            message = self.messenger.get_message()
            self.handle_message(message)

    def close(self):
        """Application cleanup."""
        self.socket_server.close()









