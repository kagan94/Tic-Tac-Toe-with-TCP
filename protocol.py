#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Setup Python logging --------------------------------------------------------
import logging

FORMAT = '%(asctime)-15s %(levelname)s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
LOG = logging.getLogger()


# Info--------------------------------------------------------------------------
___NAME = "Protocol to the online document editor"
___VER = "0.0.3"


def info():
    return '%s version %s' % (___NAME, ___VER)


# Imports----------------------------------------------------------------------
from socket import error as socket_error
import select

# Extend our PYTHONPATH for working directory----------------------------------
import os
from sys import path, argv
a_path = os.path.sep.join(os.path.abspath(argv[0]).split(os.path.sep)[:-1])
path.append(a_path)


# Local copies of files on the client side
current_path = os.path.abspath(os.path.dirname(__file__))
client_files_dir = os.path.join(current_path, "client_local_files")


# Common -----------------------------------------------------------------------
SERVER_PORT = 7778
SERVER_INET_ADDR = '127.0.0.1'

BUFFER_SIZE = 1024  # Receive not more than 1024 bytes per 1 msg
SEP = ".."  # separate command and data in request
DATA_SEP = ":)"
TIMEOUT = 5  # in seconds
TERM_CHAR = "|.|"


# "Enum" for commands
def enum(**vals):
    return type('Enum', (), vals)

COMMAND = enum(
    # From client to the Server
    START_NEW_GAME='1',
    JOIN_GAME='2',
    GAMES_LIST='3',
    MAKE_MOVE='4',

    # Notifications from the server
    NOTIFICATION=enum(
        YOU_LOST='10',
        YOU_WON='11',
        YOUR_TURN='12',
        GAME_IS_A_TIE='13'
    )
)


# Responses
RESP = enum(
    OK='0',
    FAIL='1',
    GAME_DOES_NOT_EXIST='2',
    GAME_ALREADY_STARTED='3',
    MOVE_IS_INVALID='4'
)


# Main functions ---------------------------------------------------------------
def error_code_to_string(err_code):
    '''
    :param err_code: code of the error
    :return: (string) defenition of the error
    '''
    global RESP

    err_text = ""

    if err_code == RESP.OK:
        err_text = "No errors"
    elif err_code == RESP.FAIL:
        err_text = "Bad result."
    elif err_code == RESP.PERMISSION_ERROR:
        err_text = "Permissions error."
    elif err_code == RESP.FILE_ALREADY_EXISTS:
        err_text = "Requested file already exists."
    elif err_code == RESP.FILE_DOES_NOT_EXIST:
        err_text = "Requested file doesn't exist."
    return err_text


def tcp_send(sock, data):
    '''
    :param sock: socket
    :param data: (list)
    :return:
    '''
    query = SEP.join([str(el) for el in data]) + TERM_CHAR

    try:
        sock.sendall(query)
        return True
    except:
        return False


def tcp_receive(sock, buffer_size=BUFFER_SIZE):
    '''
    :param sock: TCP socket
    :param buffer_size: max possible size of message per one receive call
    :return: message without terminate characters
    '''
    m = ''
    while 1:
        try:
            # Check if there is data available before call recv
            ready, _, _ = select.select([sock], [], [])

            # Nothing is received yet
            if not ready:
                return None

            # ready to receive
            else:
                # Receive one block of data according to receive buffer size
                block = sock.recv(buffer_size)
                m += block

        except socket_error as (code, msg):
            if code == 10054:
                LOG.error('Server is not available.')
            else:
                LOG.error('Socket error occurred. Error code: %s, %s' % (code, msg))
            return None

        # if m.endswith(TERM_CHAR) or len(block) <= 0:
        if m.endswith(TERM_CHAR):
            break

    # return m
    return m[:-len(TERM_CHAR)]


def parse_query(raw_data):
    '''
    :param raw_data: string that may contain command and data
    :return: (command, data)
    '''
    # Split string by separator to get the command and data
    command, data = raw_data.split(SEP)
    return command, data


def parse_response(response):
    ''' Parse response from the server '''
    command, resp_code, data = response.split(SEP)
    return command, resp_code, data


def close_socket(sock, log_msg=""):
    # Check if the socket is closed already
    # in this case there can be no I/O descriptor
    try:
        sock.fileno()
    except socket_error:
        LOG.debug('Socket closed already ...')
        return

    # Close socket, remove I/O descriptor
    sock.close()

    if len(log_msg) > 0:
        LOG.debug(log_msg)


# This function is used in client.py
# (need to parse get_file response)
# NOTICE: Content should not be splitted, because it may contain separator
def parse_get_file_response(raw_data):
    '''
    :param data: raw_data
    :return: am_i_owner (Boolean), file_access (enum), content (string)
    '''
    cleaned_data = raw_data.split(SEP)
    am_i_owner, file_access = cleaned_data[:2]

    two_args_length = sum(len(s) for s in cleaned_data[:2]) + 2
    content = raw_data[two_args_length:]

    return am_i_owner, file_access, content


# Used in both client.py/server.py
def pack_data(data):
    '''
    :param target_list: (list)
    :return: joined list elements by separator
    '''
    content = DATA_SEP.join([str(el) for el in data])
    return content


def parse_data(raw_data):
    cleaned_data = raw_data.split(DATA_SEP)
    return cleaned_data
