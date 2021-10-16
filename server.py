#!/usr/bin/env python3

import socket
import json
from _thread import *

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
ThreadCount = 0

server_id = "s1"
userlist = {}

# Chatroomlist = [“roomid”: ”serverid”]
# Mychatrooms =  [“roomid”:[[”owner”,”serverid”],[“user1”,”user2”,”user3”,..]]]
# Chatservers = [“serverid”:”state”]


def threaded_client(conn):
    thread_owner=None
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except:
                if thread_owner is not None:
                    del userlist[thread_owner]
                    break
            data = json.loads(data.decode("utf-8"))
            print(data)

            if data['type'] == 'newidentity':
                if (data['identity'] in userlist) or (not data['identity'].isalnum()) or (not 3<=len(data['identity'])<=16):
                    conn.sendall(json.dumps({"type": "newidentity", "approved": "false"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
                    break
                else:
                    # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader
                    leader_to_all_servers = json.dumps({"type" : "newidentity", "identity" : "Adel", "approved" : "true", "serverid" : "s1"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    leader_response = json.loads(leader_to_all_servers.decode("utf-8"))
                    if leader_response['approved'] == 'false':
                        conn.sendall(
                            json.dumps({"type": "newidentity", "approved": "false"}, ensure_ascii=False).encode(
                                'utf8') + '\n'.encode('utf8'))
                        break
                    elif leader_response['approved'] == 'true':
                        userlist[(data['identity'])] = server_id
                        thread_owner = data['identity']
                        reply1 = json.dumps({"type": "newidentity", "approved": "true"}, ensure_ascii=False).encode(
                            'utf8') + '\n'.encode('utf8')
                        reply2 = json.dumps(
                            {"type": "roomchange", "identity": "Adel", "former": "", "roomid": "MainHall-s1"},
                            ensure_ascii=False).encode('utf8') + '\n'.encode('utf8')
                        conn.sendall(reply1 + reply2)
                    else:
                        print("Error occured in newidentity operation")
                        break

            elif data['type'] == 'createroom':
                pass
            elif data['type'] == 'list':
                print('list')
            elif data['type'] == 'who':
                print('who')
                conn.sendall(json.dumps({"type": "roomcontents", "roomid": "jokes",
                                         "identities": list(userlist.keys()),
                                         "owner": thread_owner}, ensure_ascii=False).encode('utf8') + '\n'.encode(
                    'utf8'))
            elif data['type'] == 'quit':
                print('#quit: Client requested to close the connection')
                if thread_owner is not None:
                    del userlist[thread_owner]
                    conn.sendall(json.dumps({"type": "quit", "approved": "true"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
                    break
            else:
                continue



# while True:
#     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     try:
#         s.bind((HOST, PORT))
#         s.listen()
#         conn, addr = s.accept()
#         print('Connected to: ' + addr[0] + ':' + str(addr[1]))
#         start_new_thread(threaded_client, (conn,))
#         ThreadCount += 1
#         print('Thread Number: ' + str(ThreadCount))
#     finally:
#         s.close()
#         print("Clode connection")

while True:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        print('Connected to: ' + addr[0] + ':' + str(addr[1]))
        start_new_thread(threaded_client, (conn,))
        ThreadCount += 1
        print('Thread Number: ' + str(ThreadCount))




#python server.py
#java -jar client.jar -h 127.0.0.1 -p 65432 -i Adel -d
#java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 65432 -i Adel1

