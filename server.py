#!/usr/bin/env python3

import socket
import json
from _thread import *


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
            sendall_json(client.conn, room_change_notification)
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
                sendall_json(client.conn, room_change_notification)
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
                sendall_json(client.conn, {"type": "message", "identity": sent_by.id, "content": message})

    def get_client_id_list(self):
        client_id_list = []
        for client in self.clientList:
            client_id_list.append(client.id)
        return client_id_list


def user_owns_chat_room(client):
    for i in server.myChatRooms:
        if server.myChatRooms[i].owner == client:
            return True
    return False


def sendall_json(conn, payload):
    try:
        conn.sendall(json.dumps(payload, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
    except(ConnectionResetError, OSError):
        pass


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

    def remove_client_from_the_server(self, client):
        if user_owns_chat_room(client):
            server.delete_chat_room(client.room)
        client.room.remove_client_from_the_room(client, None)
        del self.userList[client.id]
        sendall_json(client.conn,
                     {"type": "roomchange", "identity": client.id, "former": client.room.name, "roomid": ""})
        conn.close()

    def delete_chat_room(self, chat_room):
        chat_room.about_to_delete = True
        for client in chat_room.clientList:
            if chat_room.owner != client:
                client.join_room(self.myChatRooms["MainHall-" + self.server_id])
        del self.all_chat_rooms_in_the_system[chat_room.name]
        del self.myChatRooms[chat_room.name]
        sendall_json(chat_room.owner.conn, {"type": "deleteroom", "roomid": chat_room.name, "approved": "true"})
        chat_room.owner.join_room(server.myChatRooms["MainHall-" + server.server_id])


server_id = "s1"
owner_of_the_server = Owner("")
server = Server(server_id, '127.0.0.1', 65432, 5555, owner_of_the_server)


class Client:
    def __init__(self, id, conn, server_id):
        self.id = id
        self.conn = conn
        self.server_id = server_id
        self.room = None
        self.room = server.myChatRooms["MainHall-" + server_id].add_client(self)

    def join_room(self, destination_room):
        if self.room.remove_client_from_the_room(self, destination_room):
            destination_room.add_client(self)
            return True
        return False


def threaded_client(conn):
    thread_owner = None
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except:
                if thread_owner is not None:
                    server.remove_client_from_the_server(thread_owner)
                    break
            data = json.loads(data.decode("utf-8"))
            print(data)

            if data['type'] == 'newidentity':
                if (data['identity'] in server.userList) or (not data['identity'].isalnum()) or (
                        not 3 <= len(data['identity']) <= 16):
                    sendall_json(conn, {"type": "newidentity", "approved": "false"})
                    break
                else:
                    # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader
                    leader_to_all_servers = json.dumps(
                        {"type": "newidentity", "identity": "Adel", "approved": "true", "serverid": "s1"},
                        ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                    if leader_response['approved'] == 'false':
                        sendall_json(conn, {"type": "newidentity", "approved": "false"})
                        break
                    elif leader_response['approved'] == 'true':
                        sendall_json(conn, {"type": "newidentity", "approved": "true"})
                        thread_owner = Client(data['identity'], conn, server.server_id)
                        server.userList[data['identity']] = thread_owner
                    else:
                        print("Error occurred in newidentity operation")
                        break

            elif data['type'] == 'list':
                print('#list')
                sendall_json(conn, {"type": "roomlist", "rooms": list(server.myChatRooms.keys())})

            elif data['type'] == 'who':
                print('who')
                sendall_json(conn, {"type": "roomcontents", "roomid": thread_owner.room.name,
                                    "identities": thread_owner.room.get_client_id_list(),
                                    "owner": thread_owner.room.owner.id})
            elif data['type'] == 'createroom':
                if (data['roomid'] in server.myChatRooms) or (user_owns_chat_room(thread_owner)) or (
                        not data['roomid'].isalnum()) or (
                        not 3 <= len(data['roomid']) <= 16):
                    sendall_json(conn, {"type": "createroom", "roomid": data['roomid'], "approved": "false"})
                else:
                    # Server sends {"type" : "createroom", "roomid" : data['roomid'], “clientid” : “Adel”} to the leader
                    leader_to_all_servers = json.dumps(
                        {"type": "createroom", "roomid": data['roomid'], "clientid": "Adel", "serverid": "s1",
                         "approved": "true"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                    if leader_response['approved'] == 'false':
                        sendall_json(conn,
                                     {"type": "createroom", "roomid": leader_response['roomid'], "approved": "false"})

                    elif leader_response['approved'] == 'true':
                        server.myChatRooms[leader_response['roomid']] = ChatRoom(leader_response['roomid'],
                                                                                 thread_owner, server.server_id)
                        server.all_chat_rooms_in_the_system[leader_response['roomid']] = server.myChatRooms[
                            leader_response['roomid']]
                        sendall_json(conn,
                                     {"type": "createroom", "roomid": leader_response['roomid'], "approved": "true"})
                        thread_owner.join_room(server.myChatRooms[leader_response['roomid']])
                    else:
                        print("Error occurred in createroom operation")
            elif data['type'] == 'joinroom':
                if data['roomid'] not in server.all_chat_rooms_in_the_system or user_owns_chat_room(thread_owner):
                    sendall_json(conn,
                                 {"type": "roomchange", "identity": "Maria", "former": "jokes", "roomid": "jokes"})
                elif data['roomid'] in server.myChatRooms:
                    thread_owner.join_room(server.myChatRooms[data['roomid']])
                elif data['roomid'] in server.all_chat_rooms_in_the_system:
                    sendall_json(conn, {"type": "route", "roomid": "jokes", "host": "122.134.2.4", "port": "4445"})
                    server.remove_client_from_the_server(thread_owner)
            elif data['type'] == 'movejoin':
                thread_owner = Client(data['identity'], conn, server.server_id)
                server.userList[data['identity']] = thread_owner
                if data['roomid'] not in server.myChatRooms:
                    thread_owner.join_room("MainHall-" + server.server_id)
                else:
                    thread_owner.join_room(data['roomid'])
                sendall_json(conn, {"type": "serverchange", "approved": "true", "serverid": server.server_id})
            elif data['type'] == 'deleteroom':
                if not user_owns_chat_room(thread_owner):
                    sendall_json(conn, {"type": "deleteroom", "roomid": data['roomid'], "approved": "false"})
                else:
                    server.delete_chat_room(server.myChatRooms[data['roomid']])
            elif data['type'] == 'message':
                if data['content'] != '':
                    thread_owner.room.message_broadcast(data['content'], thread_owner)
            elif data['type'] == 'quit':
                print('#quit: Client requested to close the connection')
                if thread_owner is not None:
                    server.remove_client_from_the_server(thread_owner)
                    break
            else:
                continue


# HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
# PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
ThreadCount = 0

while True:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((server.server_address, server.clients_port))
        s.listen()
        conn, addr = s.accept()
        print('Connected to: ' + addr[0] + ':' + str(addr[1]))
        start_new_thread(threaded_client, (conn,))
        ThreadCount += 1
        print('Thread Number: ' + str(ThreadCount))

# python server.py
# java -jar client.jar -h 127.0.0.1 -p 65432 -i Adel -d
# java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 65432 -i Adel1
