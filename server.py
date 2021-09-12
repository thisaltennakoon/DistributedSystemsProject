#!/usr/bin/env python3

import socket
import json
from _thread import *

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
ThreadCount = 0
clients = []

def threaded_client(conn):
    with conn:
        # print('Connected by', addr)
        while True:
            data = conn.recv(1024)
            # print('Client : ',data)
            # print(type(data))
            data = json.loads(data.decode("utf-8"))
            print(data)
            if data['type'] == 'newidentity':
                if data['identity'] not in clients:
                    clients.append(data['identity'])
                    reply1 = json.dumps({"type": "newidentity", "approved": "true"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8')
                    reply2 = json.dumps(
                        {"type": "roomchange", "identity": "Adel", "former": "", "roomid": "MainHall-s1"},
                        ensure_ascii=False).encode('utf8') + '\n'.encode('utf8')
                    conn.sendall(reply1 + reply2)
                else:
                    conn.sendall(json.dumps({"type": "newidentity", "approved": "false"}, ensure_ascii=False).encode(
                        'utf8') + '\n'.encode('utf8'))
            elif data == b'{"type" : "list"}\n':
                print('list')
            elif data == b'{"type" : "who"}\n':
                print('who')
            else:
                break

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

