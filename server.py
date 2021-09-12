#!/usr/bin/env python3

import socket
import json

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

while True:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            #print('Connected by', addr)
            while True:
                data = conn.recv(1024)
                print('Client : ',data)

                if data == b'{"identity":"Adel","type":"newidentity"}\n':
                    reply1 = json.dumps({"type" : "newidentity", "approved" : "true"}, ensure_ascii=False).encode('utf8')+'\n'.encode('utf8')
                    reply2 = json.dumps({"type" : "roomchange", "identity" : "Adel", "former" : "", "roomid" : "MainHall-s1"}, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8')
                    conn.sendall(reply1+reply2)
                elif data == b'{"type" : "list"}\n':
                    print('list')
                elif data == b'{"type" : "who"}\n':
                    print('who')
                else:
                    break


#python echo-server.py

