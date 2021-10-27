import random
import socket
import json
from _thread import *
import argparse
import threading
import time
from time import sleep


class Owner:
    def __init__(self, id):
        self.id = id


class ChatRoom:
    def __init__(self, name, owner, server):
        self.name = name
        self.owner = owner
        self.server = server
        self.clientList = []
        self.about_to_delete = False

    def add_client(self, newClient):
        if newClient.connection is not None:
            self.clientList.append(newClient)
            if newClient.room is None:
                former = ""
            else:
                former = newClient.room.name
            newClient.room = self
            room_change_notification = {"type": "roomchange", "identity": newClient.id, "former": former,
                                        "roomid": self.name}
            for client in self.clientList:
                self.server.sendall_json(
                    client.connection, room_change_notification)
            print("Client " + newClient.id +
                  " added to the " + self.name + " chatroom")
            return self

    def remove_client_from_the_room(self, client, destination_room):
        if self.owner != client:
            self.clientList.remove(client)
            if destination_room is None:
                destination_room_name = ""
            else:
                destination_room_name = destination_room.name
            room_change_notification = {"type": "roomchange", "identity": client.id, "former": self.name,
                                        "roomid": destination_room_name}
            for client in self.clientList:
                self.server.sendall_json(
                    client.connection, room_change_notification)
            print("Client " + client.id +
                  " has been removed from " + self.name + " chatroom")
            return True
        elif self.owner == client and self.about_to_delete:
            print("Final notification from the chat room: " +
                  self.name + " before deleting.Good Bye!")
            return True
        else:
            return False

    def message_broadcast(self, message, sent_by):
        a = self.clientList
        for client in self.clientList:
            if client != sent_by:
                self.server.sendall_json(client.connection,
                                         {"type": "message", "identity": sent_by.id, "content": message})

    def get_client_id_list(self):
        client_id_list = []
        for client in self.clientList:
            client_id_list.append(client.id)
        return client_id_list


class Client:
    def __init__(self, id, connection, server):
        self.id = id
        self.connection = connection
        self.server = server
        self.about_to_change_server = False
        self.room = None
        self.room = self.server.chat_system.get_chat_room(
            "MainHall-" + self.server.server_id).add_client(self)

    def join_room(self, destination_room):
        if self.room.remove_client_from_the_room(self, destination_room):
            destination_room.add_client(self)
            return True
        return False


class Server:
    def __init__(self, server_id, server_address, clients_port, coordination_port, owner, chat_system):
        self.server_id = server_id
        self.server_address = server_address
        self.clients_port = clients_port
        self.coordination_port = coordination_port
        self.chat_system = chat_system
        self.owner = owner
        self.chat_system.add_chat_room(
            ChatRoom("MainHall-" + self.server_id, owner, self))
        self.bully = Bully(server_id, chat_system)

    def run_server(self):
        start_new_thread(self.client_server_tcp_handler, ())
        server_thread_count = 0
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((self.server_address, self.coordination_port))
        s.listen()
        while True:
            connection, addr = s.accept()
            print('Connected to: ' + addr[0] + ':' + str(addr[1]))
            start_new_thread(self.threaded_server, (connection,))
            server_thread_count += 1
            print('Thread Number: ' + str(server_thread_count))

    def client_server_tcp_handler(self):
        client_thread_count = 0
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((self.server_address, self.clients_port))
        s.listen()
        while True:
            connection, addr = s.accept()
            print('Connected to: ' + addr[0] + ':' + str(addr[1]))
            start_new_thread(self.threaded_client, (connection,))
            client_thread_count += 1
            print('Thread Number: ' + str(client_thread_count))

    def remove_client_from_the_server(self, client):
        if self.user_owns_chat_room(client):
            self.delete_chat_room(client.room)
        client.room.remove_client_from_the_room(client, None)
        self.chat_system.delete_user(client)
        self.chat_system.send_to_other_servers(
            {"type": "deleteidentity", "identity": client.id})
        self.sendall_json(client.connection,
                          {"type": "roomchange", "identity": client.id, "former": client.room.name, "roomid": ""})
        client.connection.close()

    def delete_chat_room(self, chat_room):
        chat_room.about_to_delete = True
        client_list_of_the_chatroom = list(chat_room.clientList)
        for client in client_list_of_the_chatroom:
            if chat_room.owner != client:
                client.join_room(self.chat_system.get_chat_room(
                    "MainHall-" + self.server_id))

        self.chat_system.delete_chat_room(chat_room)

        self.chat_system.send_to_other_servers(
            {"type": "deleteroom", "roomid": chat_room.name})
        self.sendall_json(chat_room.owner.connection,
                          {"type": "deleteroom", "roomid": chat_room.name, "approved": "true"})
        chat_room.owner.join_room(
            self.chat_system.get_chat_room("MainHall-" + self.server_id))

    def user_owns_chat_room(self, client):
        all_chatrooms = self.chat_system.get_chat_rooms()
        for i in all_chatrooms:
            if all_chatrooms[i].owner == client:
                return True
        return False

    def sendall_json(self, connection, payload):
        try:
            print(payload)
            connection.sendall(json.dumps(payload, ensure_ascii=False).encode(
                'utf8') + '\n'.encode('utf8'))
        except(ConnectionResetError, OSError):
            pass

    def threaded_client(self, connection):
        thread_owner = None
        with connection:
            while True:
                try:
                    data = connection.recv(1024)
                except:
                    if thread_owner is not None:
                        self.remove_client_from_the_server(thread_owner)
                        break
                if data:
                    data = json.loads(data.decode("utf-8"))
                    print(data)
                else:
                    break

                if data['type'] == 'newidentity':
                    requested_user = self.chat_system.get_user(
                        data['identity'])

                    if (requested_user) or (not data['identity'].isalnum()) or (
                            not 3 <= len(data['identity']) <= 16):
                        self.sendall_json(
                            connection, {"type": "newidentity", "approved": "false"})
                        break
                    else:
                        # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader 
                        wait = True
                        while(wait):
                            try:                           
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                    s.connect((self.chat_system.servers[self.chat_system.leader].server_address,
                                            int(self.chat_system.servers[self.chat_system.leader].coordination_port)))
                                    s.sendall(json.dumps(
                                        {"type": "newidentity",
                                            "identity": data['identity'], "serverid": self.server_id},
                                        ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                                    wait = False
                                    leader_response = json.loads(
                                        s.recv(1024).decode("utf-8"))
                                    if leader_response['approved'] == 'false':
                                        self.sendall_json(
                                            connection, {"type": "newidentity", "approved": "false"})
                                        break
                                    elif leader_response['approved'] == 'true':
                                        self.sendall_json(
                                            connection, {"type": "newidentity", "approved": "true"})
                                        self.chat_system.add_user(
                                            Client(data['identity'], connection, self))
                                        thread_owner = self.chat_system.get_user(
                                            data['identity'])
                                    else:
                                        print(
                                            "Error occurred in newidentity operation")
                                        break
                            except socket.error as e:
                                #oldleader = self.chat_system.leader
                                #self.chat_system.send_to_other_servers({'type':'deleteserver','serverid':oldleader},[oldleader,self.server_id])
                                #self.chat_system.servers.pop(oldleader)
                                self.bully.run_election()
                elif data['type'] == 'list':
                    print('#list')
                    self.sendall_json(connection,
                                      {"type": "roomlist", "rooms": list(self.chat_system.get_chat_rooms().keys())})

                elif data['type'] == 'who':
                    print('who')
                    self.sendall_json(connection, {"type": "roomcontents", "roomid": thread_owner.room.name,
                                                   "identities": thread_owner.room.get_client_id_list(),
                                                   "owner": thread_owner.room.owner.id})
                elif data['type'] == 'createroom':
                    while(True):
                        try:
                            if (self.chat_system.get_chat_room(data['roomid'])) or (self.user_owns_chat_room(thread_owner)) or (
                                    not data['roomid'].isalnum()) or (
                                    not 3 <= len(data['roomid']) <= 16):
                                self.sendall_json(connection,
                                                {"type": "createroom", "roomid": data['roomid'], "approved": "false"})
                                break
                            else:
                                # Server sends {"type" : "createroom", "roomid" : data['roomid'], “clientid” : “Adel”} to the leader
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                    s.connect((self.chat_system.servers[self.chat_system.leader].server_address,
                                            int(self.chat_system.servers[self.chat_system.leader].coordination_port)))
                                    s.sendall(json.dumps(
                                        {"type": "createroom", "roomid": data['roomid'], "clientid": thread_owner.id,
                                        "serverid": thread_owner.server.server_id},
                                        ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                                    leader_response = json.loads(
                                        s.recv(1024).decode("utf-8"))

                                if leader_response['approved'] == 'false':
                                    self.sendall_json(connection,
                                                    {"type": "createroom", "roomid": leader_response['roomid'],
                                                    "approved": "false"})
                                    break
                                elif leader_response['approved'] == 'true':
                                    self.chat_system.add_chat_room(ChatRoom(leader_response['roomid'],
                                                                            thread_owner, self))

                                    self.sendall_json(connection,
                                                    {"type": "createroom", "roomid": leader_response['roomid'],
                                                    "approved": "true"})
                                    thread_owner.join_room(
                                        self.chat_system.get_chat_room(leader_response['roomid']))
                                    break
                                else:
                                    print("Error occurred in createroom operation")
                                    break
                        except socket.error as e:
                            self.bully.run_election()

                elif data['type'] == 'joinroom':
                        requested_chat_room = self.chat_system.get_chat_room(
                            data['roomid'])  # gives False or chatroom
                        if not requested_chat_room or self.user_owns_chat_room(thread_owner):
                            self.sendall_json(connection,
                                              {"type": "roomchange", "identity": thread_owner.id, "former": data['roomid'],
                                               "roomid": data['roomid']})
                        elif requested_chat_room and requested_chat_room.server == self:
                            a = requested_chat_room
                            thread_owner.join_room(requested_chat_room)
                        elif requested_chat_room and requested_chat_room.server != self:
                            current_room = self.chat_system.get_chat_room(
                                thread_owner.room.name)
                            self.chat_system.increase_vector_clock()
                            while(True):
                                try:
                                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                        s.connect((self.chat_system.servers[self.chat_system.leader].server_address,
                                                int(self.chat_system.servers[self.chat_system.leader].coordination_port)))
                                        s.sendall(json.dumps({"type": "changeserver", "currentserver": self.server_id,
                                                            "destinationserver": data['roomid'], "identity": thread_owner.id,
                                                            "vector_clock": str(self.chat_system.get_vector_clock())},
                                                            ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                                        leader_response = json.loads(
                                            s.recv(1024).decode("utf-8"))
                                        self.chat_system.increase_vector_clock(
                                            eval(leader_response['vector_clock']))
                                        if leader_response['approved'] == 'true':
                                            current_room.remove_client_from_the_room(thread_owner,
                                                                                    self.chat_system.get_chat_room(data['roomid']))
                                            thread_owner.about_to_change_server = True
                                            thread_owner.room = None
                                            thread_owner.server = None
                                            self.chat_system.increase_vector_clock()
                                            self.sendall_json(connection,
                                                            {"type": "route", "roomid": data['roomid'],
                                                            "host": self.chat_system.get_chat_room(
                                                                data['roomid']).server.server_address,
                                                            "port": str(self.chat_system.get_chat_room(

                                                                data['roomid']).server.clients_port)})
                                        break
                                except socket.error as e:
                                    self.bully.run_election()
                elif data['type'] == 'movejoin':

                    print("movejoin request received")
                    self.chat_system.increase_vector_clock()
                    thread_owner = self.chat_system.get_user(data['identity'])
                    self.chat_system.increase_vector_clock()
                    thread_owner.connection = connection
                    thread_owner.server = self
                    self.chat_system.increase_vector_clock()
                    requested_chat_room = self.chat_system.get_chat_room(
                        data['roomid'])

                    if requested_chat_room:
                        self.chat_system.increase_vector_clock()
                        requested_chat_room.clientList.append(thread_owner)
                        thread_owner.room = requested_chat_room
                        self.chat_system.increase_vector_clock()
                    else:
                        self.chat_system.increase_vector_clock()
                        main_hall_chat_room = self.chat_system.get_chat_room(
                            "MainHall-" + self.server_id)
                        main_hall_chat_room.clientList.append(thread_owner)
                        thread_owner.room = main_hall_chat_room
                        self.chat_system.increase_vector_clock()
                    self.sendall_json(connection,
                                      {"type": "serverchange", "approved": "true", "serverid": self.server_id})
                    self.chat_system.increase_vector_clock()
                    if thread_owner.room:
                        for client in thread_owner.room.clientList:
                            self.chat_system.increase_vector_clock()
                            self.sendall_json(client.connection, {"type": "roomchange", "identity": thread_owner.id,
                                                                  "former": data['former'],
                                                                  "roomid": thread_owner.room.name})
                    self.chat_system.increase_vector_clock()
                elif data['type'] == 'deleteroom':
                    if not self.user_owns_chat_room(thread_owner):
                        self.sendall_json(connection,
                                          {"type": "deleteroom", "roomid": data['roomid'], "approved": "false"})
                    else:
                        self.delete_chat_room(
                            self.chat_system.get_chat_room(data['roomid']))
                elif data['type'] == 'message':
                    if data['content'] != '' and data['content'][0] == "$":
                        if data['content'] == "$sayhello":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                        s.connect((self.chat_system.servers[server_j].server_address,
                                                   int(self.chat_system.servers[server_j].coordination_port)))
                                        s.sendall(json.dumps({"type": "sayhello", "sender": self.server_id},
                                                             ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                        elif data['content'] == "$betheleader":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                        s.connect((self.chat_system.servers[server_j][0],
                                                   int(self.chat_system.servers[server_j][2])))
                                        s.sendall(json.dumps({"type": "leader_election", "leader": self.server_id},
                                                             ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                            self.is_leader = self.server_id
                    else:
                        if data['content'] != '':
                            thread_owner.room.message_broadcast(
                                data['content'], thread_owner)
                elif data['type'] == 'quit':
                    print('#quit: Client requested to close the connection')
                    if thread_owner is not None:
                        self.remove_client_from_the_server(thread_owner)
                        break
                else:
                    continue

    def threaded_server(self, connection):
        with connection:
            data = connection.recv(1024)
            data = json.loads(data.decode("utf-8"))
            print("from server thread", data)
            if data['type'] == 'sayhello':
                print("Server: " + data["sender"] +
                      " said hello to Server: " + self.server_id)
            elif data['type'] == 'newleader':
                self.chat_system.leader = data['leaderid']
                self.bully.new_leader_msg(data["senderid"])
                print("Server: " + data['senderid'] + " said Server: " +
                      data['leaderid'] + " is the new leader")
            elif data['type'] == 'newidentity':
                requested_user = self.chat_system.get_user(data['identity'])
                if (requested_user):
                    self.sendall_json(connection,
                                      {"type": "newidentity", "identity": data['identity'], "approved": "false",
                                       "serverid": data['serverid']})
                else:
                    if data['serverid'] != self.server_id:
                        self.chat_system.add_user(Client(data['identity'], None,
                                                         self.chat_system.servers[data['serverid']]))
                        self.chat_system.get_user(data['identity']).room = None

                    self.sendall_json(connection,
                                      {"type": "newidentity", "identity": data['identity'], "approved": "true",
                                       "serverid": data['serverid']})
                    self.chat_system.send_to_other_servers(
                        {"type": "newidentity_by_leader", "identity": data['identity'], "approved": "true",
                         "serverid": data['serverid']}, [data['serverid']])
            elif data['type'] == 'newidentity_by_leader' and data['approved'] == 'true':
                self.chat_system.add_user(Client(data['identity'], None,
                                                 self.chat_system.servers[data['serverid']]))
                self.chat_system.get_user(data['identity']).room = None

            elif data['type'] == 'deleteidentity':
                self.chat_system.delete_user(
                    self.chat_system.get_user(data['identity']))
            elif data['type'] == 'createroom':
                requested_chat_room = self.chat_system.get_chat_room(
                    data['roomid'])  # gives False or chatroom
                if (requested_chat_room):
                    self.sendall_json(connection,
                                      {"type": "createroom", "roomid": data['roomid'], "clientid": data['clientid'],
                                       "serverid": data['serverid'], "approved": "false"})
                else:
                    if data['serverid'] != self.server_id:
                        self.chat_system.add_chat_room(ChatRoom(data['roomid'],
                                                                self.chat_system.servers[data['serverid']].owner,
                                                                self.chat_system.servers[data['serverid']]))

                    self.sendall_json(connection,
                                      {"type": "createroom", "roomid": data['roomid'], "clientid": data['clientid'],
                                       "serverid": data['serverid'], "approved": "true"})
                    self.chat_system.send_to_other_servers(
                        {"type": "createroom_by_leader", "roomid": data['roomid'], "clientid": data['clientid'],
                         "serverid": data['serverid'], "approved": "true"}, [data['serverid']])
            elif data['type'] == 'createroom_by_leader' and data['approved'] == 'true':
                self.chat_system.add_chat_room(ChatRoom(data['roomid'],
                                                        self.chat_system.servers[data['serverid']].owner,
                                                        self.chat_system.servers[data['serverid']]))

            elif data['type'] == 'deleteroom':
                self.chat_system.delete_chat_room(
                    self.chat_system.get_chat_room(data['roomid']))

            elif data['type'] == 'changeserver':
                self.chat_system.increase_vector_clock(
                    eval(data['vector_clock']))
                if data['currentserver'] != self.server_id:
                    requested_user = self.chat_system.get_user(
                        data['identity'])
                    requested_user.room = None
                    requested_user.server = None
                self.chat_system.increase_vector_clock()
                self.sendall_json(connection, {"type": "changeserver", "currentserver": data['currentserver'],
                                               "destinationserver": data['destinationserver'], "approved": "true",
                                               "vector_clock": str(self.chat_system.get_vector_clock())})
                self.chat_system.increase_vector_clock()
                self.chat_system.send_to_other_servers(
                    {"type": "changeserver_by_leader", "currentserver": data['currentserver'],
                     "destinationserver": data['destinationserver'], "approved": "true",
                     "identity": data['identity']}, [data['currentserver']])
                print("changeserver request from " + data['currentserver'] + " to " + data[
                    'destinationserver'] + " by " + data['identity'])

            elif data['type'] == 'changeserver_by_leader':
                self.chat_system.increase_vector_clock(
                    eval(data['vector_clock']))
                if self.chat_system.compare_vector_clock(eval(data['vector_clock'])):
                    requested_user = self.chat_system.get_user(
                        data['identity'])
                    requested_user.room = None
                    requested_user.server = None
                self.chat_system.increase_vector_clock()
            elif data["type"] == 'start_election':
                self.bully.election_msg_received(data["serverid"])
            elif data["type"] == 'tookover':
                self.bully.took_over_msg(data["serverid"])
            elif data["type"] == 'deleteserver':
                self.chat_system.servers.pop(data["serverid"])
                print("server " + data["serverid"] + "deleted from serverlist. new list =" + str(self.chat_system.servers))          


class ChatSystem:
    def __init__(self):
        self.servers = {}
        self.user_list = {}
        self.chat_rooms = {}
        self.vector_clock = {}
        self.leader = None
        self.this_server_id = self.identify_servers()
        self.server = self.servers[self.this_server_id]
        self.elect_leader()
        self.server.run_server()

    def identify_servers(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-server_id", "--server_id",
                            help="Server ID(Default=A Random Number)")
        parser.add_argument("-servers_conf", "--servers_conf",
                            help="Path to the text file containing the configuration of servers(Default=servers_conf.txt)")
        args = parser.parse_args()

        if args.server_id:
            server_id = args.server_id
            print("Starting chat server: " + server_id)

        if args.servers_conf:
            servers_conf = args.servers_conf
            print(
                "Path to the text file containing the configuration of servers: " + servers_conf)

        servers_conf_file = open(servers_conf, "r")
        servers_conf = servers_conf_file.readlines()[1:]
        for server_i in servers_conf:
            a = server_i[0:-1].split("\t")
            server_j = Server(a[0], a[1], int(
                a[2]), int(a[3]), Owner(""), self)
            self.servers[a[0]] = server_j
            self.add_chat_room(
                ChatRoom("MainHall-" + a[0], server_j.owner, server_j))
            self.vector_clock[a[0]] = 0
        print(self.servers)
        return server_id

    def elect_leader(self):
        self.leader = "s1"
        try:
            self.send_to_other_servers(
                {"type": "elected_leader", "leader": self.leader, "sender": self.this_server_id})
        except(ConnectionRefusedError):
            pass

    def is_leader(self):
        if self.leader == self.this_server_id:
            return True
        else:
            return False

    def send_to_other_servers(self, payload, eliminate=[]):
        for server_j in self.servers:
            eliminate.append(self.this_server_id)
            if server_j not in eliminate:
                self.increase_vector_clock()
                payload["vector_clock"] = str(self.get_vector_clock())
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((self.servers[server_j].server_address, int(
                        self.servers[server_j].coordination_port)))
                    s.sendall(json.dumps(payload,
                                         ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))

    def get_vector_clock(self):
        with threading.Lock():
            return self.vector_clock

    def increase_vector_clock(self, array={}):
        with threading.Lock():
            print('Old Vector Clock ', self.get_vector_clock())
            self.vector_clock[self.this_server_id] = self.vector_clock[self.this_server_id] + 1
            for i in array:
                if i != self.this_server_id:
                    self.vector_clock[i] = max(self.vector_clock[i], array[i])
            print('New Vector Clock ', self.get_vector_clock)

    def compare_vector_clock(self, array):
        with threading.Lock():
            print('System Vector Clock ', self.get_vector_clock())
            print('Received Vector Clock ', array)
            for i in array:
                if array[i] >= self.vector_clock[i]:
                    continue
                else:
                    return False
            return True

    def get_chat_room(self, chat_room):
        with threading.Lock():
            if chat_room in self.chat_rooms:
                return self.chat_rooms[chat_room]
            else:
                return False

    def get_chat_rooms(self):
        with threading.Lock():
            return self.chat_rooms

    def add_chat_room(self, chat_room):
        with threading.Lock():
            if chat_room.name not in self.chat_rooms:
                self.chat_rooms[chat_room.name] = chat_room
                return True
            else:
                return False

    def delete_chat_room(self, chat_room):
        with threading.Lock():
            if chat_room.name in self.chat_rooms:
                del self.chat_rooms[chat_room.name]
                return True
            else:
                return False

    def get_user(self, user):
        with threading.Lock():
            if user in self.user_list:
                return self.user_list[user]
            else:
                return False

    def add_user(self, user):
        with threading.Lock():
            if user.id not in self.user_list:
                self.user_list[user.id] = user
                return True
            else:
                return False

    def delete_user(self, user):
        with threading.Lock():
            if user.id in self.user_list:
                del self.user_list[user.id]
                return True
            else:
                return False


class Bully:
    def __init__(self, serverid, chatSystem):
        self.serverid = serverid
        self.nodeid = int(self.serverid[1:])
        # coordinator, coodinated, offline, election, takenover, intermediate
        self.state = "coodinated"
        self.serverList = chatSystem.servers

    def setState(self, _state):
        self.state = _state

    def getState(self):
        return self.state

    def run_election(self):
        self.setState("election")
        print("started election by the server " + str(self.serverid) + "\n")
        for i in (self.serverList):
            j = i[1:]
            if int(j) > self.nodeid:
                self.send_election_msg(i)
                print("Server " + str(self.serverid) +
                      " sends a election message to server " + str(i) + "\n")
        sleep(0.25)
        if(self.state != "takenover"):
            self.send_elected_msg()
            self.setState("coordinator")
            print("Server " + str(self.serverid) +
                  " is elected as the new leader")
        else:
            self.setState("intermediate")
        return

    def send_json_message(self, host, port, msg):
        print(self.serverid + " sends " + str(msg) + " to " + str(port))
        message = json.dumps(msg, ensure_ascii=False).encode(
            'utf8') + '\n'.encode('utf8')
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.sendall(message)
            s.close
        except socket.error:
            print("connot connect to " + host + " " + str(port))

    def send_election_msg(self, id):
        self.send_json_message(self.serverList[id].server_address, self.serverList[id].coordination_port, {
                               "type": "start_election", "serverid": self.serverid})

    def send_elected_msg(self):
        for i in self.serverList:
            self.send_json_message(self.serverList[i].server_address, self.serverList[i].coordination_port, {
                                   "type": "newleader", "leaderid": self.serverid, "senderid": self.serverid})

    def new_leader_msg(self, id):
        print("")
        self.setState("coordinated")
        # return(json.dumps({"type": "accepted"}, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))

    def took_over_msg(self, id):
        self.setState("takenover")

    def election_msg_received(self, id):
        self.setState("takenover")
        print(self.serverid + " received election msg from " + id)
        self.send_json_message(self.serverList[id].server_address, self.serverList[id].coordination_port, {
                               "type": "tookover", "serverid": self.serverid})
        if(self.getState != "election" and self.getState != "takenover"):
            self.run_election()


chat_system = ChatSystem()

# python server.py -servers_conf servers_conf.txt -server_id s1
# java -jar client.jar -h localhost -p 5556 -i gayan
