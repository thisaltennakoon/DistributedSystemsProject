#!/usr/bin/env python3

import socket
import json
from _thread import *

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
ThreadCount = 0

class Client:
    def __init__(self, id, conn, server_id):
        self.id = id
        self.conn = conn
        self.server_id = server_id
        self.room = None
        self.room = myChatRooms["MainHall-"+server_id].add_client(self)

    def join_room(self,destination_room):
        if self.room.remove_client(self):
            destination_room.add_client(self)
            return True
        return False

class ChatRoom:
    def __init__(self, name, owner, server_id):
        self.name = name
        self.owner = owner
        self.server_id = server_id
        self.clientList = []

    def add_client(self, newClient):
        self.clientList.append(newClient)
        if newClient.room is None:
            former = ""
        else:
            former = newClient.room
        room_change_notification = {"type": "roomchange", "identity": newClient.id, "former": former, "roomid": self.name}
        for client in self.clientList:
            client.conn.sendall(json.dumps(room_change_notification, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
        print("Client "+newClient.id+" added to the "+self.name+" chatroom")

        return self

    def remove_client(self, client):
        if self.owner != client:
            self.clientList.remove(client)
            print("Client "+client.id+" has been removed from "+self.name+" chatroom")
            return True
        else:
            return False

    def broadcastMessage(message):
        print("Broadcasting message to all")


def user_owns_chat_room(user_id):
    for i in myChatRooms:
        if i.owner == user_id:
            return True
    return False

server_id = "s1"
userList = []  #Stores Client objects

chatRoomList = {}  # {“roomid”: ”serverid”}
myChatRooms = {"MainHall-"+server_id:ChatRoom("MainHall-"+server_id,server_id,server_id)}  # [“roomid”:[[”owner”,”serverid”],[“user1”,”user2”,”user3”,..]]]


# Chatservers = [“serverid”:”state”]




def threaded_client(conn):
    thread_owner = None
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except:
                if thread_owner is not None:
                    userList.remove(thread_owner)
                    break
            data = json.loads(data.decode("utf-8"))
            print(data)

            if data['type'] == 'newidentity':
                if (data['identity'] in userList) or (not data['identity'].isalnum()) or (
                not 3 <= len(data['identity']) <= 16):
                    conn.sendall(json.dumps({"type": "newidentity", "approved": "false"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
                    break
                else:
                    # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader
                    leader_to_all_servers = json.dumps(
                        {"type": "newidentity", "identity": "Adel", "approved": "true", "serverid": "s1"},
                        ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                    if leader_response['approved'] == 'false':
                        conn.sendall(
                            json.dumps({"type": "newidentity", "approved": "false"}, ensure_ascii=False).encode(
                                'utf8') + '\n'.encode('utf8'))
                        break
                    elif leader_response['approved'] == 'true':
                        conn.sendall(json.dumps({"type": "newidentity", "approved": "true"}, ensure_ascii=False).encode(
                            'utf8') + '\n'.encode('utf8'))
                        thread_owner = Client(data['identity'],conn,server_id)
                        userList.append(thread_owner)
                    else:
                        print("Error occured in newidentity operation")
                        break
            #######################################################################################################################

            elif data['type'] == 'createroom':
                if (data['roomid'] in chatRoomList) or (user_owns_chat_room(thread_owner)) or (
                not data['roomid'].isalnum()) or (
                        not 3 <= len(data['roomid']) <= 16):
                    conn.sendall(json.dumps({"type": "createroom", "roomid": "jokes", "approved": "false"},
                                            ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
                else:
                    # Server sends {"type" : "createroom", "roomid" : "jokes", “clientid” : “Adel”} to the leader
                    leader_to_all_servers = json.dumps(
                        {"type": "createroom", "roomid": "jokes", "clientid": "Adel", "serverid": "s1",
                         "approved": "true"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                    if leader_response['approved'] == 'false':
                        conn.sendall(
                            json.dumps({"type": "createroom", "roomid": "jokes", "approved": "false"},
                                       ensure_ascii=False).encode(
                                'utf8') + '\n'.encode('utf8'))

                    elif leader_response['approved'] == 'true':
                        myChatRooms[leader_response['roomid']] = ChatRoom(leader_response['roomid'],thread_owner,server_id)
                        conn.sendall(
                            json.dumps({"type": "createroom", "roomid": "jokes", "approved": "true"},
                                       ensure_ascii=False).encode(
                                'utf8') + '\n'.encode('utf8'))
                    else:
                        print("Error occured in createroom operation")
            #######################################################################################################################
            elif data['type'] == 'deleteroom':
                if not user_owns_chat_room(thread_owner):
                    conn.sendall(
                        json.dumps({"type" : "deleteroom", "roomid" : "jokes", "approved" : "false"},
                                   ensure_ascii=False).encode(
                            'utf8') + '\n'.encode('utf8'))
                else:
                    #Server sends {"type" : "deleteroom", "serverid" : "s1", "roomid" : "jokes"} to the leader and leader sends {"type" : "deleteroom", "serverid" : "s1", "roomid" : "jokes", "approved" : "true"} to all the other servers. Then all the servers deletes the particular chat room from the chatroomlist and server owning the chat room,
                    pass
################################################################################################################################
            elif data['type'] == 'list':
                print('list')
            elif data['type'] == 'who':
                print('who')
                conn.sendall(json.dumps({"type": "roomcontents", "roomid": "jokes",
                                         "identities": list(userList.keys()),
                                         "owner": thread_owner}, ensure_ascii=False).encode('utf8') + '\n'.encode(
                    'utf8'))
            elif data['type'] == 'quit':
                print('#quit: Client requested to close the connection')
                if thread_owner is not None:
                    del userList[thread_owner]
                    conn.sendall(json.dumps({"type": "quit", "approved": "true"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
                    break
            else:
                continue


while True:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        print('Connected to: ' + addr[0] + ':' + str(addr[1]))
        start_new_thread(threaded_client, (conn,))
        ThreadCount += 1
        print('Thread Number: ' + str(ThreadCount))

# python server.py
# java -jar client.jar -h 127.0.0.1 -p 65432 -i Adel -d
# java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 65432 -i Adel1
