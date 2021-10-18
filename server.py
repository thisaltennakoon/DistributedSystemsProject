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
    def __init__(self, name, owner, server_id):
        self.name = name
        self.owner = owner
        self.server_id = server_id
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
            server.sendall_json(client.connection, room_change_notification)
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
                server.sendall_json(client.connection, room_change_notification)
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
                server.sendall_json(client.connection, {"type": "message", "identity": sent_by.id, "content": message})

    def get_client_id_list(self):
        client_id_list = []
        for client in self.clientList:
            client_id_list.append(client.id)
        return client_id_list


class Client:
    def __init__(self, id, connection, server_id):
        self.id = id
        self.connection = connection
        self.server_id = server_id
        self.room = None
        self.room = server.myChatRooms["MainHall-" + server_id].add_client(self)

    def join_room(self, destination_room):
        if self.room.remove_client_from_the_room(self, destination_room):
            destination_room.add_client(self)
            return True
        return False


class Server:
    def __init__(self, server_id, server_address, clients_port, coordination_port, owner):
        self.server_id = server_id
        self.server_address = server_address
        self.clients_port = clients_port
        self.coordination_port = coordination_port
        self.userList = {}
        self.myChatRooms = {"MainHall-" + self.server_id: ChatRoom("MainHall-" + self.server_id, owner, self.server_id)}
        self.all_chat_rooms_in_the_system = {
            "MainHall-" + self.server_id: self.myChatRooms["MainHall-" + self.server_id]}

    def run_server(self):
        ThreadCount = 0
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.server_address, self.clients_port))
                s.listen()
                connection, addr = s.accept()
                print('Connected to: ' + addr[0] + ':' + str(addr[1]))
                start_new_thread(self.threaded_client, (connection,))
                ThreadCount += 1
                print('Thread Number: ' + str(ThreadCount))

    def remove_client_from_the_server(self, client):
        if self.user_owns_chat_room(client):
            self.delete_chat_room(client.room)
        client.room.remove_client_from_the_room(client, None)
        del self.userList[client.id]
        self.sendall_json(client.connection,
                          {"type": "roomchange", "identity": client.id, "former": client.room.name, "roomid": ""})
        client.connection.close()

    def delete_chat_room(self, chat_room):
        chat_room.about_to_delete = True
        client_list_of_the_chatroom = list(chat_room.clientList)
        for client in client_list_of_the_chatroom:
            if chat_room.owner != client:
                client.join_room(self.myChatRooms["MainHall-" + self.server_id])
        del self.all_chat_rooms_in_the_system[chat_room.name]
        del self.myChatRooms[chat_room.name]
        self.sendall_json(chat_room.owner.connection,
                          {"type": "deleteroom", "roomid": chat_room.name, "approved": "true"})
        chat_room.owner.join_room(self.myChatRooms["MainHall-" + self.server_id])

    def user_owns_chat_room(self, client):
        for i in self.myChatRooms:
            if self.myChatRooms[i].owner == client:
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
                    if (data['identity'] in self.userList) or (not data['identity'].isalnum()) or (
                            not 3 <= len(data['identity']) <= 16):
                        self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                        break
                    else:
                        # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader
                        leader_to_all_servers = json.dumps(
                            {"type": "newidentity", "identity": "Adel", "approved": "true", "serverid": "s1"},
                            ensure_ascii=False).encode(
                            'utf8') + '\n'.encode('utf8')
                        leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                        if leader_response['approved'] == 'false':
                            self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                            break
                        elif leader_response['approved'] == 'true':
                            self.sendall_json(connection, {"type": "newidentity", "approved": "true"})
                            thread_owner = Client(data['identity'], connection, self.server_id)
                            self.userList[data['identity']] = thread_owner
                        else:
                            print("Error occurred in newidentity operation")
                            break

                elif data['type'] == 'list':
                    print('#list')
                    self.sendall_json(connection, {"type": "roomlist", "rooms": list(self.myChatRooms.keys())})

                elif data['type'] == 'who':
                    print('who')
                    self.sendall_json(connection, {"type": "roomcontents", "roomid": thread_owner.room.name,
                                                   "identities": thread_owner.room.get_client_id_list(),
                                                   "owner": thread_owner.room.owner.id})
                elif data['type'] == 'createroom':
                    if (data['roomid'] in self.myChatRooms) or (self.user_owns_chat_room(thread_owner)) or (
                            not data['roomid'].isalnum()) or (
                            not 3 <= len(data['roomid']) <= 16):
                        self.sendall_json(connection,
                                          {"type": "createroom", "roomid": data['roomid'], "approved": "false"})
                    else:
                        # Server sends {"type" : "createroom", "roomid" : data['roomid'], “clientid” : “Adel”} to the leader
                        leader_to_all_servers = json.dumps(
                            {"type": "createroom", "roomid": data['roomid'], "clientid": "Adel", "serverid": "s1",
                             "approved": "true"}, ensure_ascii=False).encode(
                            'utf8') + '\n'.encode('utf8')
                        leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                        if leader_response['approved'] == 'false':
                            self.sendall_json(connection,
                                              {"type": "createroom", "roomid": leader_response['roomid'],
                                               "approved": "false"})

                        elif leader_response['approved'] == 'true':
                            self.myChatRooms[leader_response['roomid']] = ChatRoom(leader_response['roomid'],
                                                                                   thread_owner, self.server_id)
                            self.all_chat_rooms_in_the_system[leader_response['roomid']] = self.myChatRooms[
                                leader_response['roomid']]
                            self.sendall_json(connection,
                                              {"type": "createroom", "roomid": leader_response['roomid'],
                                               "approved": "true"})
                            thread_owner.join_room(self.myChatRooms[leader_response['roomid']])
                        else:
                            print("Error occurred in createroom operation")
                elif data['type'] == 'joinroom':
                    if data['roomid'] not in self.all_chat_rooms_in_the_system or self.user_owns_chat_room(
                            thread_owner):
                        self.sendall_json(connection,
                                          {"type": "roomchange", "identity": "Maria", "former": "jokes",
                                           "roomid": "jokes"})
                    elif data['roomid'] in self.myChatRooms:
                        thread_owner.join_room(self.myChatRooms[data['roomid']])
                    elif data['roomid'] in self.all_chat_rooms_in_the_system:
                        self.sendall_json(connection,
                                          {"type": "route", "roomid": "jokes", "host": "122.134.2.4", "port": "4445"})
                        self.remove_client_from_the_server(thread_owner)
                elif data['type'] == 'movejoin':
                    thread_owner = Client(data['identity'], connection, self.server_id)
                    self.userList[data['identity']] = thread_owner
                    if data['roomid'] not in self.myChatRooms:
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
                        self.delete_chat_room(self.myChatRooms[data['roomid']])
                elif data['type'] == 'message':
                    if data['content'] != '':
                        thread_owner.room.message_broadcast(data['content'], thread_owner)
                elif data['type'] == 'quit':
                    print('#quit: Client requested to close the connection')
                    if thread_owner is not None:
                        self.remove_client_from_the_server(thread_owner)
                        break
                else:
                    continue


server_id = str(int(random.random() * 10000000))
server_address = '127.0.0.1'
clients_port = 4444
coordination_port = 5555

parser = argparse.ArgumentParser()

# Adding optional argument
parser.add_argument("-server_id", "--server_id", help="Server ID(Default=A Random Number)")
parser.add_argument("-server_address", "--server_address", help="Server Address(Default=127.0.0.1)")
parser.add_argument("-clients_port", "--clients_port", help="Clients Port(Default=4444)")
parser.add_argument("-coordination_port", "--coordination_port", help="Coordination Port(Default=5555)")

# Read arguments from command line
args = parser.parse_args()

if args.server_id:
    server_id = args.server_id
    print("Starting chat server: " + server_id)

if args.server_address:
    server_address = args.server_address
    print("Server Address: " + server_address)

if args.clients_port:
    try:
        clients_port = int(args.clients_port)
        print("Clients Port: " + str(clients_port))
    except ValueError:
        print("Please enter an integer between 0-65353")

if args.coordination_port:
    try:
        coordination_port = int(args.coordination_port)
        print("Coordination Port: " + str(coordination_port))
    except ValueError:
        print("Please enter an integer between 0-65353")

server = Server(server_id, server_address, clients_port, coordination_port, Owner(""))
server.run_server()

# python server.py -server_id s1 -server_address 127.0.0.1 -clients_port 4444 -coordination_port 5555
# java -jar client.jar -h 127.0.0.1 -p 65432 -i Adel -d
# java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 4444 -i Adel1
