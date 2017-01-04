#! /usr/bin/env python
# -*- coding: utf-8 -*-

'''
    The code for Tic-Tac-Toe game
    was partially taken from this source:
    http://inventwithpython.com/tictactoe.py
'''


# Setup Python logging --------------------------------------------------------
import logging
FORMAT = '%(asctime)-15s %(levelname)s %(message)s'
logging.basicConfig(level=logging.DEBUG,format=FORMAT)
LOG = logging.getLogger()
LOG.info('Client-side started working...')


# Imports----------------------------------------------------------------------
import time
from argparse import ArgumentParser  # Parsing command line arguments
from socket import AF_INET, SOCK_STREAM, socket, error as socket_error
from threading import Thread, Lock
from protocol import *


class Client(object):
    def __init__(self, host, port):
        self.lock = Lock()

        self.exit = False
        self.wait = False

        # Client's socket
        self.sock = None
        self.sock_port = int(port)
        self.sock_host = host

        self.game_id = None
        self.my_turn = False
        self.game_end = False

    # Declare client socket and connecting
    def connect(self):
        self.sock = socket(AF_INET, SOCK_STREAM)

        try:
            self.sock.connect((self.sock_host, self.sock_port))
        except socket_error as (code, msg):
            if code == 10061:
                LOG.error('Socket error occurred. Server does not respond.')
            else:
                LOG.error('Socket error occurred. Error code: %s, %s' % (code, msg))
            return None
        else:
            LOG.info('Connection is established successfully')

        LOG.info('TCP Socket created and start to connect..')
        return self.sock

    def disconnect(self):
        '''
        Disconnect from the server by closing the socket.
        Close socket it there're some problems.
        '''
        close_socket(self.sock, "Close client socket.")

    def request(self, command, data=""):
        ''' This method sends the given request to server '''
        tcp_send(self.sock, [command, data])
        LOG.debug("Command %s was sent to server" % command)

    def make_move(self):
        # Let the player type in his move.
        move = ' '
        while move not in '1 2 3 4 5 6 7 8 9'.split():
            move = raw_input("What is your next move? (1-9): ")

        # Request to the server to make move
        data = pack_data([self.game_id, move])
        self.request(COMMAND.MAKE_MOVE, data)

    def start_game(self):
        self.game_end = False

        print "Field structure:"
        print "7|8|9"
        print "4|5|6"
        print "1|2|3"
        print "-----"

        try:
            # Until the game is finished, player can play
            while not self.game_end:
                # print "my_turn", self.my_turn

                if not self.my_turn:
                    # Start the game here
                    time.sleep(0.3)

                else:
                    self.make_move()
                    self.my_turn = False

        except KeyboardInterrupt:
            self.exit = True
            self.wait = False
            LOG.debug('Ctrl+C issued ...')

    def draw_board(self, board):
        ''' This function prints out the board that it was passed '''
        # "board" is a list of 10 strings representing the board (ignore index 0)
        print("#" * 11)
        print('   |   |')
        print(' ' + board[7] + ' | ' + board[8] + ' | ' + board[9])
        print('   |   |')
        print('-----------')
        print('   |   |')
        print(' ' + board[4] + ' | ' + board[5] + ' | ' + board[6])
        print('   |   |')
        print('-----------')
        print('   |   |')
        print(' ' + board[1] + ' | ' + board[2] + ' | ' + board[3])
        print('   |   |')

    def main_app_loop(self):
        def all_possible_commands():
            text = "Next commands are available:\n"
            text += "'gl' - to request a games list\n"
            text += "'ng' - to start a new game\n"
            text += "'jg' - to join existing game\n"
            text += "'exit' - to exit from the app\n"
            print text

        MENU_COOMAND = enum(
            GAMES_LIST="gl",
            START_NEW_GAME="ng",
            JOIN_GAME="jg",
            EXIT="exit",
        )

        try:
            # Infinite loop, until the user wants to exit
            while not self.exit:
                self.wait = False

                print "\nYou're in the main menu"
                # Show all possible commands that client can request
                all_possible_commands()

                try:
                    command = raw_input("Please, enter a command: \n")
                except KeyboardInterrupt:
                    LOG.debug('Ctrl+C issued ...')
                    command = 'exit'

                if command == MENU_COOMAND.GAMES_LIST:
                    self.request(COMMAND.GAMES_LIST)

                elif command == MENU_COOMAND.START_NEW_GAME:
                    self.request(COMMAND.START_NEW_GAME)
                    self.wait = True

                elif command == MENU_COOMAND.JOIN_GAME:
                    game_id = raw_input("Enter game_id: ").strip()
                    self.request(COMMAND.JOIN_GAME, data=game_id)
                    self.wait = True

                elif command == MENU_COOMAND.EXIT:
                    with self.lock:
                        self.exit = True
                    break

                else:
                    print "Unrecognized command"

                # If we need to wait some time (during game process or waiting for response),
                # do timeout with 0.5 sec, until we will receive response
                while self.wait:
                    time.sleep(0.5)

                # If the game started and now we can play, then
                if self.game_id:
                    self.start_game()

        except KeyboardInterrupt:
            self.exit = True
            LOG.debug('Ctrl+C issued ...')

    # Loop for iterating over received notifications
    def notifications_loop(self):
        logging.info('Falling into notifier loop ...')

        try:
            n_fails = 0

            # Will receive notification until the app terminated
            while not self.exit:
                m = tcp_receive(self.sock)

                # If total number of failures more than 5, then exit..
                if n_fails > 5:
                    break

                # Some problem with receiving occurred or just need to wait
                if m is None:
                    time.sleep(0.3)
                    n_fails += 1
                    continue

                # Reset total "failures" counter
                n_fails = 0

                LOG.info('Notification is received: %s' % m)
                command, resp_code, data = parse_response(m)

                if command == COMMAND.START_NEW_GAME:
                    # board = [' '] * 10
                    # self.draw_board(board)

                    print "Now you need to wait until someone will be connected"

                    with self.lock:
                        self.game_id = data
                        self.wait = False

                elif command == COMMAND.JOIN_GAME:
                    if resp_code == RESP.GAME_DOES_NOT_EXIST:
                        print "Game with requested id doesn't exist"
                        with self.lock:
                            self.game_id = None

                    elif resp_code == RESP.GAME_ALREADY_STARTED:
                        print "Game already started"
                        with self.lock:
                            self.game_id = None

                    elif resp_code == RESP.OK:
                        with self.lock:
                            self.game_id = data

                        # board = [' '] * 10
                        # self.draw_board(board)

                        print "Now you need to you wait for your move..."
                    with self.lock:
                        self.wait = False

                elif command == COMMAND.GAMES_LIST:
                    # Game ids list which have not started yet
                    games = parse_data(data)

                    if games and games[0] != "":
                        print "Available games: \n %s" % "\n".join(games)
                    else:
                        print "No available games"

                elif command == COMMAND.MAKE_MOVE:
                    if resp_code == RESP.MOVE_IS_INVALID:
                        print "Your move is invalid. Please do again your move"
                        with self.lock:
                            self.my_turn = True

                    # Turn was made successfully
                    else:
                        board = parse_data(data)
                        self.draw_board(board)

                #################
                # Notifications
                elif command == COMMAND.NOTIFICATION.YOUR_TURN:
                    # Draw the field in current state
                    board = parse_data(data)
                    self.draw_board(board)

                    print "It's your turn"
                    with self.lock:
                        self.my_turn = True

                elif command in [COMMAND.NOTIFICATION.GAME_IS_A_TIE,
                                 COMMAND.NOTIFICATION.YOU_WON,
                                 COMMAND.NOTIFICATION.YOU_LOST]:
                    # Draw the field in current state
                    board = parse_data(data)
                    self.draw_board(board)

                    print "Game ended"

                    if command == COMMAND.NOTIFICATION.YOU_WON:
                        print "You won!"
                    elif command == COMMAND.NOTIFICATION.YOU_LOST:
                        print "You lost!"
                    else:
                        print "It's a tie, nobody won.."

                    with self.lock:
                        self.game_end = True
                        self.game_id = None

                        # Run main menu again
                        self.wait = False

        except KeyboardInterrupt:
            # self.sock.shutdown(SHUT_WR)
            LOG.debug('Ctrl+C issued ...')

        with self.lock:
            self.exit = True
            self.wait = False

        print 'Terminating from "notifications" loop thread ...'


# Main part of client application
def main(args):
    client = Client(host=args.host, port=args.port)

    # Check if the socket was created correctly, if no then exit..
    if not client.connect():
        return

    # Create 2 separate threads for asynchronous notifications and for main app
    main_app_thread = Thread(name='MainApplicationThread', target=client.main_app_loop)
    notifications_thread = Thread(name='NotificationsThread', target=client.notifications_loop)

    main_app_thread.start()
    notifications_thread.start()

    # Exit only when client requested to exit
    try:
        while not client.exit:
            time.sleep(0.2)
    except KeyboardInterrupt, IOError:
        LOG.debug('Ctrl+C issued (or IOError)...')
        client.exit = True

    # Close client (socket) connection
    client.disconnect()

    print 'Terminating ...'

    # Blocks until the thread finished the work.
    main_app_thread.join()
    notifications_thread.join()


if __name__ == '__main__':
    # Parsing arguments
    parser = ArgumentParser(description=info())
    parser.add_argument('-H', '--host',
                        help='Server INET address (to connect) )'
                             'defaults to %s' % SERVER_INET_ADDR,
                        default=SERVER_INET_ADDR)
    parser.add_argument('-p', '--port', type=int,
                        help='Server TCP port (to connect), '
                             'defaults to %d' % SERVER_PORT,
                        default=SERVER_PORT)
    args = parser.parse_args()
    main(args)

    print 'App was terminated ...'
