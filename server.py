#!/usr/bin/env python3
import random
import socket
import json
from _thread import *
import argparse


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
        self.clientList.append(newClient)
        if newClient.room is None:
            former = ""
        else:
            former = newClient.room.name
        newClient.room = self
        room_change_notification = {"type": "roomchange", "identity": newClient.id, "former": former,
                                    "roomid": self.name}
        for client in self.clientList:
            self.server.sendall_json(client.connection, room_change_notification)
        print("Client " + newClient.id + " added to the " + self.name + " chatroom")
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
                self.server.sendall_json(client.connection, room_change_notification)
            print("Client " + client.id + " has been removed from " + self.name + " chatroom")
            return True
        elif self.owner == client and self.about_to_delete:
            print("Final notification from the chat room: " + self.name + " before deleting.Good Bye!")
            return True
        else:
            return False

    def message_broadcast(self, message, sent_by):
        for client in self.clientList:
            if client != sent_by:
                self.server.sendall_json(client.connection, {"type": "message", "identity": sent_by.id, "content": message})

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
        self.room = None
        self.room = server.chat_rooms["MainHall-" + self.server.server_id].add_client(self)

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
        self.user_list = chat_system.user_list
        self.chat_rooms = chat_system.chat_rooms
        self.owner = owner
        self.chat_rooms["MainHall-" + self.server_id] = ChatRoom("MainHall-" + self.server_id, owner, self)


    def run_server(self):
        start_new_thread(self.client_server_tcp_handler, ())
        server_thread_count = 0
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.server_address, self.coordination_port))
                s.listen()
                connection, addr = s.accept()
                print('Connected to: ' + addr[0] + ':' + str(addr[1]))
                start_new_thread(self.threaded_server, (connection,))
                server_thread_count += 1
                print('Thread Number: ' + str(server_thread_count))

    def client_server_tcp_handler(self):
        client_thread_count = 0
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.server_address, self.clients_port))
                s.listen()
                connection, addr = s.accept()
                print('Connected to: ' + addr[0] + ':' + str(addr[1]))
                start_new_thread(self.threaded_client, (connection,))
                client_thread_count += 1
                print('Thread Number: ' + str(client_thread_count))


    def remove_client_from_the_server(self, client):
        if self.user_owns_chat_room(client):
            self.delete_chat_room(client.room)
        client.room.remove_client_from_the_room(client, None)
        del self.user_list[client.id]
        self.sendall_json(client.connection,
                          {"type": "roomchange", "identity": client.id, "former": client.room.name, "roomid": ""})
        client.connection.close()

    def delete_chat_room(self, chat_room):
        chat_room.about_to_delete = True
        client_list_of_the_chatroom = list(chat_room.clientList)
        for client in client_list_of_the_chatroom:
            if chat_room.owner != client:
                client.join_room(self.chat_rooms["MainHall-" + self.server_id])
        # del self.all_chat_rooms_in_the_system[chat_room.name]
        del self.chat_rooms[chat_room.name]
        # del self.chat_system.chat_rooms[chat_room.name]
        self.chat_system.send_to_other_servers({"type": "deleteroom", "roomid": chat_room.name})
        self.sendall_json(chat_room.owner.connection,
                          {"type": "deleteroom", "roomid": chat_room.name, "approved": "true"})
        chat_room.owner.join_room(self.chat_rooms["MainHall-" + self.server_id])

    def user_owns_chat_room(self, client):
        for i in self.chat_rooms:
            if self.chat_rooms[i].owner == client:
                return True
        return False

    def sendall_json(self, connection, payload):
        try:
            connection.sendall(json.dumps(payload, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
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
                data = json.loads(data.decode("utf-8"))
                print(data)

                if data['type'] == 'newidentity':
                    if (data['identity'] in self.user_list) or (not data['identity'].isalnum()) or (
                            not 3 <= len(data['identity']) <= 16):
                        self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                        break
                    else:
                        # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader

                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((self.chat_system.servers[self.chat_system.leader].server_address, int(self.chat_system.servers[self.chat_system.leader].coordination_port)))
                            s.sendall(json.dumps({"type" : "newidentity", "identity" : data['identity'], "serverid" : self.server_id},
                                                 ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                            leader_response = json.loads(s.recv(1024).decode("utf-8"))
                            if leader_response['approved'] == 'false':
                                self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                                break
                            elif leader_response['approved'] == 'true':
                                self.sendall_json(connection, {"type": "newidentity", "approved": "true"})
                                thread_owner = Client(data['identity'], connection, self)
                                self.user_list[data['identity']] = thread_owner

                            else:
                                print("Error occurred in newidentity operation")
                                break

                elif data['type'] == 'list':
                    print('#list')
                    self.sendall_json(connection, {"type": "roomlist", "rooms": list(self.chat_system.chat_rooms.keys())})

                elif data['type'] == 'who':
                    print('who')
                    self.sendall_json(connection, {"type": "roomcontents", "roomid": thread_owner.room.name,
                                                   "identities": thread_owner.room.get_client_id_list(),
                                                   "owner": thread_owner.room.owner.id})
                elif data['type'] == 'createroom':
                    if (data['roomid'] in self.chat_rooms) or (self.user_owns_chat_room(thread_owner)) or (
                            not data['roomid'].isalnum()) or (
                            not 3 <= len(data['roomid']) <= 16):
                        self.sendall_json(connection,
                                          {"type": "createroom", "roomid": data['roomid'], "approved": "false"})
                    else:
                        # Server sends {"type" : "createroom", "roomid" : data['roomid'], “clientid” : “Adel”} to the leader

                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((self.chat_system.servers[self.chat_system.leader].server_address, int(self.chat_system.servers[self.chat_system.leader].coordination_port)))
                            s.sendall(json.dumps({"type" : "createroom", "roomid" : data['roomid'], "clientid" : thread_owner.id, "serverid": thread_owner.server.server_id},
                                                 ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                            leader_response = json.loads(s.recv(1024).decode("utf-8"))

                        if leader_response['approved'] == 'false':
                            self.sendall_json(connection,
                                              {"type": "createroom", "roomid": leader_response['roomid'],
                                               "approved": "false"})

                        elif leader_response['approved'] == 'true':
                            self.chat_rooms[leader_response['roomid']] = ChatRoom(leader_response['roomid'],
                                                                                   thread_owner, self)
                            # self.all_chat_rooms_in_the_system[leader_response['roomid']] = self.chat_rooms[
                            #     leader_response['roomid']]
                            self.sendall_json(connection,
                                              {"type": "createroom", "roomid": leader_response['roomid'],
                                               "approved": "true"})
                            thread_owner.join_room(self.chat_rooms[leader_response['roomid']])
                        else:
                            print("Error occurred in createroom operation")
                elif data['type'] == 'joinroom':
                    if (data['roomid'] not in self.chat_system.chat_rooms and data['roomid'] not in self.chat_rooms) or self.user_owns_chat_room(
                            thread_owner):
                        self.sendall_json(connection,
                                          {"type": "roomchange", "identity": thread_owner.id, "former": data['roomid'],
                                           "roomid": data['roomid']})
                    elif data['roomid'] in self.chat_rooms:
                        thread_owner.join_room(self.chat_rooms[data['roomid']])
                    elif data['roomid'] in self.chat_system.chat_rooms:

                        self.sendall_json(connection,
                                          {"type": "route", "roomid": data['roomid'], "host":
                                              self.chat_system.servers[self.chat_system.chat_rooms[data['roomid']]][0],
                                           "port":
                                               self.chat_system.servers[self.chat_system.chat_rooms[data['roomid']]][
                                                   1]})
                        self.remove_client_from_the_server(thread_owner)
                elif data['type'] == 'movejoin':
                    thread_owner = Client(data['identity'], connection, self.server_id)
                    self.user_list[data['identity']] = thread_owner
                    if data['roomid'] not in self.chat_rooms:
                        thread_owner.join_room("MainHall-" + self.server_id)
                    else:
                        thread_owner.join_room(data['roomid'])
                    self.sendall_json(connection,
                                      {"type": "serverchange", "approved": "true", "serverid": self.server_id})
                elif data['type'] == 'deleteroom':
                    if not self.user_owns_chat_room(thread_owner):
                        self.sendall_json(connection,
                                          {"type": "deleteroom", "roomid": data['roomid'], "approved": "false"})
                    else:
                        self.delete_chat_room(self.chat_rooms[data['roomid']])
                elif data['type'] == 'message':
                    if data['content'] != '' and data['content'][0] == "$":
                        if data['content'] == "$sayhello":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                        s.connect((self.chat_system.servers[server_j][0], int(self.chat_system.servers[server_j][2])))
                                        s.sendall(json.dumps({"type": "sayhello", "sender": self.server_id},
                                                             ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                        elif data['content'] == "$betheleader":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                        s.connect((self.chat_system.servers[server_j][0], int(self.chat_system.servers[server_j][2])))
                                        s.sendall(json.dumps({"type": "leader_election", "leader": self.server_id},
                                                             ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
                            self.is_leader = self.server_id
                    else:
                        if data['content'] != '':
                            thread_owner.room.message_broadcast(data['content'], thread_owner)
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
                print("Server: " + data["sender"] + " said hello to Server: " + self.server_id)
            elif data['type'] == 'leader_election':
                self.chat_system.leader = data["leader"]
                print("Server: " + data["sender"] + " said Server: " + data["leader"] + " is the new leader")
            elif data['type'] == 'newidentity':
                if (data['identity'] in self.chat_system.user_list):
                    self.sendall_json(connection,
                                      {"type": "newidentity", "identity": data['identity'], "approved": "false",
                                       "serverid": data['serverid']})
                else:
                    self.chat_system.user_list[data['identity']] = data['serverid']
                    self.sendall_json(connection,
                                      {"type": "newidentity", "identity": data['identity'], "approved": "true",
                                       "serverid": data['serverid']})
                    self.chat_system.send_to_other_servers(
                        {"type": "newidentity_by_leader", "identity": data['identity'], "approved": "true",
                         "serverid": data['serverid']})
            elif data['type'] == 'newidentity_by_leader' and data['approved'] == 'true':
                self.chat_system.user_list[data['identity']] = data['serverid']
                self.user_list[data['identity']] = data['serverid']
            elif data['type'] == 'createroom':
                if (data['roomid'] in self.chat_system.chat_rooms):
                    self.sendall_json(connection,
                                      {"type": "createroom", "roomid": data['roomid'], "clientid": data['clientid'],
                                       "serverid": data['serverid'], "approved": "false"})
                else:
                    self.chat_system.chat_rooms[data['roomid']] = data['serverid']
                    self.sendall_json(connection,
                                      {"type": "createroom", "roomid": data['roomid'], "clientid": data['clientid'],
                                       "serverid": data['serverid'], "approved": "true"})
                    self.chat_system.send_to_other_servers(
                        {"type": "createroom_by_leader", "roomid": data['roomid'], "clientid": data['clientid'],
                         "serverid": data['serverid'], "approved": "true"})
            elif data['type'] == 'createroom_by_leader' and data['approved'] == 'true':
                self.chat_system.chat_rooms[data['roomid']] = data['serverid']
                # self.chat_rooms[data['roomid']] = data['serverid']
            elif data['type'] == 'deleteroom':
                del self.chat_system.chat_rooms[data['roomid']]


class ChatSystem:
    def __init__(self):
        self.servers = {}
        self.user_list = {}
        self.chat_rooms = {}
        self.leader = None
        self.this_server_id = self.identify_servers()
        self.server = self.servers[self.this_server_id]
        self.elect_leader()
        self.server.run_server()


    def identify_servers(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-server_id", "--server_id", help="Server ID(Default=A Random Number)")
        parser.add_argument("-servers_conf", "--servers_conf",
                            help="Path to the text file containing the configuration of servers(Default=servers_conf.txt)")
        args = parser.parse_args()

        if args.server_id:
            server_id = args.server_id
            print("Starting chat server: " + server_id)

        if args.servers_conf:
            servers_conf = args.servers_conf
            print("Path to the text file containing the configuration of servers: " + servers_conf)

        servers_conf_file = open(servers_conf, "r")
        servers_conf = servers_conf_file.readlines()[1:]
        for server_i in servers_conf:
            a = server_i[0:-1].split("\t")
            server_j = Server(a[0], a[1], int(a[2]), int(a[3]), Owner(""), self)
            self.servers[a[0]] = server_j
            self.chat_rooms["MainHall-" + a[0]] = ChatRoom("MainHall-" + a[0], server_j.owner, server_j)
        print(self.servers)
        return server_id

    def elect_leader(self):
        self.leader = "s1"
        try:
            self.send_to_other_servers({"type": "leader_election", "leader": self.leader, "sender": self.this_server_id})
        except(ConnectionRefusedError):
            pass

    def send_to_other_servers(self, payload):
        for server_j in self.servers:
            if server_j != self.this_server_id:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((self.servers[server_j].server_address, int(self.servers[server_j].coordination_port)))
                    s.sendall(json.dumps(payload,
                                         ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
chat_system = ChatSystem()
# server_id, server_address, clients_port, coordination_port, owner, chat_system):
# python 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\server.py' -server_id s2 -servers_conf 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\servers_conf.txt'
# java -jar client.jar -h 127.0.0.1 -p 65432 -i Adel -d
# java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 4444 -i Adel1

# f = open("servers_conf.txt", "a")
# f.write("serverid\tserver_address\tclients_port\tcoordination_port\ns1\tlocalhost\t4444\t5555\ns2\tlocalhost\t4445\t5556\ns3\t192.168.1.2\t4444\t5000\n")
# f.close()
