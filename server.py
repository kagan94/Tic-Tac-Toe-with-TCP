#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Setup Python logging -------------------------------------------------------
import logging

FORMAT = '%(asctime)-15s %(levelname)s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
LOG = logging.getLogger()


# Imports----------------------------------------------------------------------
import threading
from protocol import *
from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, socket, error as socket_error


class Server(object):
    def __init__(self):
        ''' Initialize "sessions" queue to collect client sessions '''
        self.sessions = {}
        self.notifications = {}  # in format <player_id>: notification
        self.games = {}  # in format <game_id>: {name: x, game_started: (0/1), opponent_id: (int)/None}
        
        self.lock = threading.Lock()
        self.game_id = 1  # initial game_id

    def main_loop(self):
        ''' Main server loop. There server accepts clients and collect them into the session queue '''
        LOG.info('Application started and server socket created')

        s = socket(AF_INET, SOCK_STREAM)
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

        try:
            s.bind((SERVER_INET_ADDR, SERVER_PORT))
        except socket_error as (code, msg):
            if code == 10048:
                LOG.error("Server already started working..")
            return

        player_id = 1

        # Socket in the listening state
        LOG.info("Waiting for a client connection...")

        # If we want to limit # of connections, then change 0 to # of possible connections
        s.listen(0)

        while True:
            try:
                # Client connected
                client_socket, addr = s.accept()
                LOG.debug("New Client connected.")

                session = ClientSession(client_socket, player_id, server=self)
                self.sessions[str(player_id)] = session
                session.start()

                # Update the value of player id for the next player
                player_id += 1

            except KeyboardInterrupt:
                LOG.info("Terminating by keyboard interrupt...")
                break
            except socket_error as err:
                LOG.error("Socket error - %s" % err)

        # Terminating application
        close_socket(s, 'Close server socket.')

    def send_notifications(self):
        '''Function to notify other clients about changes'''

        while self.notifications:
            # Each change was packed in the following format [command, [arg1, arg2, arg_n]]
            target_player_id = list(self.notifications.keys())[0]
            command, game_id = self.notifications[target_player_id]

            board = self.games[game_id]["board"]
            data = pack_data(board)

            del self.notifications[target_player_id]

            target_thread = self.sessions[target_player_id]

            # Send notification to user
            tcp_send(target_thread.client_sock, [command, RESP.OK, data])
            # t.notify(command)


# Main handler ---------------------------------------------------
class ClientSession(threading.Thread):
    def __init__(self, client_sock, player_id, server):
        threading.Thread.__init__(self)
        
        self.client_sock = client_sock
        self.server = server  # Server object
        self.player_id = str(player_id)

    def run(self):
        global dir_files, lock

        current_thread = threading.current_thread()
        connection_n = current_thread.getName().split("-")[1]
        current_thread.socket = self.client_sock

        LOG.debug("Client %s connected:" % connection_n)
        LOG.debug("Client's socket info : %s:%d:" % self.client_sock.getsockname())

        while True:
            msg = tcp_receive(self.client_sock)

            # Msg received successfully
            if msg:
                command, data = parse_query(msg)
                LOG.debug("Client's request (%s) - %s|%s" % (self.client_sock.getsockname(), command, data[:20] + "..."))

            # Case: some problem with receiving data
            else:
                LOG.debug("Client(%s) closed the connection" % connection_n)
                break

            resp_code, sending_data = RESP.OK, ""

            #######################
            # Actions on commands
            if command == COMMAND.START_NEW_GAME:
                with self.server.lock:
                    game_id = str(self.server.game_id)

                    # Create new game
                    self.server.games[game_id] = {
                        # "id": str(game_id),
                        "game_started": 0,
                        "owner_id": self.player_id,
                        "opponent_id": None,
                        "board": [' '] * 10
                    }
                    self.server.game_id += 1
                sending_data = game_id

            elif command == COMMAND.JOIN_GAME:
                game_id = data

                if game_id not in self.server.games.keys():
                    resp_code = RESP.GAME_DOES_NOT_EXIST

                elif self.server.games[game_id]["game_started"]:
                    resp_code = RESP.GAME_ALREADY_STARTED

                # Assign this player as opponent to the game and notify admin that the game started
                else:
                    with self.server.lock:
                        self.server.games[game_id]["game_started"] = 1
                        self.server.games[game_id]["opponent_id"] = self.player_id
                    owner_id = self.server.games[game_id]["owner_id"]

                    # Put notification about player's turn into the queue
                    self.server.notifications[owner_id] = [COMMAND.NOTIFICATION.YOUR_TURN, game_id]

                    sending_data = game_id

            elif command == COMMAND.GAMES_LIST:
                try:
                    # Show only the games which have not started yet
                    sending_data = pack_data(
                        [game_id for game_id, game in self.server.games.items() if not game["game_started"]])
                except KeyError:
                    sending_data = ""

            elif command == COMMAND.MAKE_MOVE:
                game_id, move = parse_data(data)

                board = self.server.games[game_id]["board"]

                # Owner will always have "X" and opponent "O"
                if self.server.games[game_id]["owner_id"] == self.player_id:
                    player_letter = 'X'
                    next_player_id = self.server.games[game_id]["opponent_id"]
                    # winner_id, loser_id = self.player_id, next_player_id
                else:
                    player_letter = 'O'
                    next_player_id = self.server.games[game_id]["owner_id"]
                    # winner_id, loser_id = next_player_id, self.player_id

                opponent_letter = 'O' if player_letter == 'X' else 'X'

                # If the space is free and move is valid, then save move
                if self.is_space_free(board, move) and move in '1 2 3 4 5 6 7 8 9'.split():
                    move = int(move)

                    board[move] = player_letter
                    sending_data = pack_data(board)

                    # If current player is winner, notify him that he lost and I won
                    if self.is_winner(board, player_letter):
                        self.server.notifications[self.player_id] = [COMMAND.NOTIFICATION.YOU_WON, game_id]
                        self.server.notifications[next_player_id] = [COMMAND.NOTIFICATION.YOU_LOST, game_id]

                    # If opponent is winner, notify him that he won and me that I lost
                    elif self.is_winner(board, opponent_letter):
                        self.server.notifications[next_player_id] = [COMMAND.NOTIFICATION.YOU_WON, game_id]
                        self.server.notifications[self.player_id] = [COMMAND.NOTIFICATION.YOU_LOST, game_id]

                    # Notify both players that game is a tie
                    elif self.is_board_full(board):
                        self.server.notifications[self.player_id] = [COMMAND.NOTIFICATION.GAME_IS_A_TIE, game_id]
                        self.server.notifications[next_player_id] = [COMMAND.NOTIFICATION.GAME_IS_A_TIE, game_id]

                    else:
                        # Notify next player about his move
                        self.server.notifications[next_player_id] = [COMMAND.NOTIFICATION.YOUR_TURN, game_id]

                # Otherwise player should make a move again
                # because move is invalid
                else:
                    resp_code = RESP.MOVE_IS_INVALID

            # Send response on requested command
            res = tcp_send(self.client_sock, [command, resp_code, sending_data])

            # Case: some problem with receiving data
            if not res:
                LOG.debug("Client(%s, %s) closed the connection" % self.client_sock.getsockname())
                break

            # Trigger notify_clients function (if there're some changes in the queue, it will process them)
            self.server.send_notifications()

        close_socket(self.client_sock, 'Close client socket.')

    def is_space_free(self, board, i):
        return board[int(i)] == ' '

    def is_board_full(self, board):
        # Return True if every space on the board has been taken. Otherwise return False.
        for i in range(1, 10):
            if self.is_space_free(board, i):
                return False
        return True

    def is_winner(self, bo, le):
        '''
        :param bo: - board
        :param le: - letter ("O" or "X")
        :return: Bool (True if the player is winner)
        '''
        # Given a board and a player's letter, this function returns True if that player has won.
        # We use bo instead of board and le instead of letter so we don't have to type as much.
        return ((bo[7] == le and bo[8] == le and bo[9] == le) or  # across the top
                (bo[4] == le and bo[5] == le and bo[6] == le) or  # across the middle
                (bo[1] == le and bo[2] == le and bo[3] == le) or  # across the bottom
                (bo[7] == le and bo[4] == le and bo[1] == le) or  # down the left side
                (bo[8] == le and bo[5] == le and bo[2] == le) or  # down the middle
                (bo[9] == le and bo[6] == le and bo[3] == le) or  # down the right side
                (bo[7] == le and bo[5] == le and bo[3] == le) or  # diagonal
                (bo[9] == le and bo[5] == le and bo[1] == le))    # diagonal


def main():
    server = Server()
    server.main_loop()


if __name__ == '__main__':
    main()
