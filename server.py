#!/usr/bin/env python3
import random
import socket
import json
from _thread import *
import argparse
import threading
from time import sleep
from concurrent import futures

import grpc

from proto import route_pb2, route_pb2_grpc
from proto.grpc_connection import GrpcConnections


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
        self.room = self.server.chat_system.get_chat_room("MainHall-" + self.server.server_id).add_client(self)

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
        self.chat_system.add_chat_room(ChatRoom("MainHall-" + self.server_id, owner, self))
        self.stub = GrpcConnections.create_stub(self.server_address, self.coordination_port)
        self.bully = Bully(server_id, chat_system)
        self.server_live = 'True'

    def set_server_live(self, value):
        with threading.Lock():
            self.server_live = value

    def get_server_live(self):
        with threading.Lock():
            return self.server_live

    def threaded_heartbeat(self):
        while True:

            if (self.chat_system.is_leader()):
                changes_count = 0
                sleep(4)
                eliminate = []
                eliminate.append(self.server_id)
                for server_j in self.chat_system.servers:
                    if server_j not in eliminate:
                        try:
                            response = self.chat_system.stubs[server_j].is_live(route_pb2.HeartBeatCheker(isLive="isLive"))  # todo

                            if self.chat_system.servers[server_j].get_server_live() == 'False':
                                changes_count+= 1
                                self.chat_system.servers[server_j].set_server_live(response.isLive)
                        except grpc.RpcError as e:

                            if self.chat_system.servers[server_j].get_server_live() == 'True':
                                changes_count+= 1
                                self.chat_system.servers[server_j].set_server_live('False')
                            pass
                if changes_count > 0:
                    print("Termination/Addition of servers identified!")

    def run_grpc_server(self):
        start_new_thread(self.client_server_tcp_handler, ())
        start_new_thread(self.threaded_heartbeat, ())
        while True:
            self.grpc_server()

    def client_server_tcp_handler(self):
        client_thread_count = 0
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.server_address, self.clients_port))
                s.listen()
                connection, addr = s.accept()
                print('Connected to: ' + addr[0] + ':' + str(addr[1]))
                start_new_thread(self.threaded_client_grpc, (connection,))
                client_thread_count += 1
                print('Thread Number: ' + str(client_thread_count))

    def remove_client_from_the_server(self, client):
        if self.user_owns_chat_room(client):
            self.delete_chat_room(client.room)
        client.room.remove_client_from_the_room(client, None)
        self.chat_system.delete_user(client)
        # self.chat_system.send_to_other_servers({"type": "deleteidentity", "identity": client.id})
        for server_j in self.chat_system.servers:
            if server_j != self.server_id:
                try:
                    response = self.chat_system.stubs[server_j].deleteIdentity(
                        route_pb2.DelIdRequest(client_id=client.id))
                except grpc.RpcError as e:
                    print('Cannot connect to the server:', str(server_j))
                    pass

        self.sendall_json(client.connection,
                          {"type": "roomchange", "identity": client.id, "former": client.room.name, "roomid": ""})
        client.connection.close()

    def delete_chat_room(self, chat_room):
        chat_room.about_to_delete = True
        client_list_of_the_chatroom = list(chat_room.clientList)
        for client in client_list_of_the_chatroom:
            if chat_room.owner != client:
                client.join_room(self.chat_system.get_chat_room("MainHall-" + self.server_id))

        self.chat_system.delete_chat_room(chat_room)
        # self.chat_system.send_to_other_servers({"type": "deleteroom", "roomid": chat_room.name})
        for server_j in self.chat_system.servers:
            if server_j != self.server_id:
                try:
                    response = self.chat_system.stubs[server_j].deleteRoom(
                        route_pb2.DelRoomRequest(room_id=chat_room.name))
                except grpc.RpcError as e:
                    print('Cannot connect to the server:', str(server_j))
                    pass
        self.sendall_json(chat_room.owner.connection,
                          {"type": "deleteroom", "roomid": chat_room.name, "approved": "true"})
        chat_room.owner.join_room(self.chat_system.get_chat_room("MainHall-" + self.server_id))

    def user_owns_chat_room(self, client):
        all_chatrooms = self.chat_system.get_chat_rooms()
        for i in all_chatrooms:
            if all_chatrooms[i].owner == client:
                return True
        return False

    def sendall_json(self, connection, payload):
        try:
            print(payload)
            connection.sendall(json.dumps(payload, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
        except(ConnectionResetError, OSError):
            pass

    def threaded_client_grpc(self, connection):
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
                    self.remove_client_from_the_server(thread_owner)
                    break

                if data['type'] == 'newidentity':
                    requested_user = self.chat_system.get_user(data['identity'])
                    if (requested_user) or (not data['identity'].isalnum()) or (
                            not 3 <= len(data['identity']) <= 16):
                        self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                        break
                    else:
                        # Server sends {"type" : "newidentity", "identity" : "Adel", “serverid” : “s1”} to the leader
                        wait = True
                        while (wait):
                            try:
                                leader_response = self.chat_system.stubs[self.chat_system.get_leader()].identityApproval(
                                    route_pb2.IdApprovalRequest(client_id=data['identity'], server_id=self.server_id))
                                wait = False
                                if leader_response.approval == 'false':
                                    self.sendall_json(connection, {"type": "newidentity", "approved": "false"})
                                    break
                                elif leader_response.approval == 'true':
                                    self.sendall_json(connection, {"type": "newidentity", "approved": "true"})
                                    self.chat_system.add_user(Client(data['identity'], connection, self))
                                    thread_owner = self.chat_system.get_user(data['identity'])
                                else:
                                    print("Error occurred in newidentity operation")
                                    break
                            except grpc.RpcError as e:
                                print('Cannot connect to the server:', str(self.chat_system.get_leader()))
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
                    if (self.chat_system.get_chat_room(data['roomid'])) or (self.user_owns_chat_room(thread_owner)) or (
                            not data['roomid'].isalnum()) or (
                            not 3 <= len(data['roomid']) <= 16):
                        self.sendall_json(connection,
                                          {"type": "createroom", "roomid": data['roomid'], "approved": "false"})

                    else:
                        wait = True
                        while (wait):
                            try:
                                # Server sends {"type" : "createroom", "roomid" : data['roomid'], “clientid” : “Adel”} to the leader
                                leader_response = self.chat_system.stubs[self.chat_system.get_leader()].roomApproval(
                                    route_pb2.RoomApprovalRequest(room_id=data['roomid'], client_id=thread_owner.id,
                                                                  server_id=thread_owner.server.server_id))

                                if leader_response.approval == 'false':
                                    self.sendall_json(connection,
                                                      {"type": "createroom", "roomid": leader_response.room_id,
                                                       "approved": "false"})

                                elif leader_response.approval == 'true':
                                    self.chat_system.add_chat_room(ChatRoom(leader_response.room_id,
                                                                            thread_owner, self))

                                    self.sendall_json(connection,
                                                      {"type": "createroom", "roomid": leader_response.room_id,
                                                       "approved": "true"})
                                    thread_owner.join_room(self.chat_system.get_chat_room(leader_response.room_id))

                                else:
                                    print("Error occurred in createroom operation")
                                wait = False
                            except grpc.RpcError as e:
                                print('Cannot connect to the server:', str(self.chat_system.get_leader()))
                                self.bully.run_election()
                elif data['type'] == 'joinroom':
                    requested_chat_room = self.chat_system.get_chat_room(data['roomid'])  # gives False or chatroom
                    if not requested_chat_room or self.user_owns_chat_room(thread_owner):
                        self.sendall_json(connection,
                                          {"type": "roomchange", "identity": thread_owner.id, "former": data['roomid'],
                                           "roomid": data['roomid']})
                    elif requested_chat_room and requested_chat_room.server == self:
                        a = requested_chat_room
                        thread_owner.join_room(requested_chat_room)
                    elif requested_chat_room and requested_chat_room.server != self:
                        current_room = self.chat_system.get_chat_room(thread_owner.room.name)
                        self.chat_system.increase_vector_clock()
                        while (True):
                            try:

                                leader_response = self.chat_system.stubs[self.chat_system.leader].changeServerApproval(
                                    route_pb2.ChangeServerApprovalRequest(current_server_id=self.server_id,
                                                                          destination_server_id=data['roomid'],
                                                                          client_id=thread_owner.id,
                                                                          vector_clock=str(
                                                                              self.chat_system.get_vector_clock())))

                                self.chat_system.increase_vector_clock(eval(leader_response.vector_clock))
                                if leader_response.approval == 'true':
                                    current_room.remove_client_from_the_room(thread_owner,
                                                                             self.chat_system.get_chat_room(
                                                                                 data['roomid']))
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
                            except grpc.RpcError as e:
                                print('Cannot connect to the server:', str(self.chat_system.get_leader()))
                                self.bully.run_election()
                elif data['type'] == 'movejoin':

                    print("movejoin request received")
                    self.chat_system.increase_vector_clock()
                    thread_owner = self.chat_system.get_user(data['identity'])
                    self.chat_system.increase_vector_clock()
                    thread_owner.connection = connection
                    thread_owner.server = self
                    self.chat_system.increase_vector_clock()
                    requested_chat_room = self.chat_system.get_chat_room(data['roomid'])

                    if requested_chat_room:
                        self.chat_system.increase_vector_clock()
                        requested_chat_room.clientList.append(thread_owner)  ######
                        thread_owner.room = requested_chat_room
                        self.chat_system.increase_vector_clock()
                    else:
                        self.chat_system.increase_vector_clock()
                        main_hall_chat_room = self.chat_system.get_chat_room("MainHall-" + self.server_id)
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
                        self.delete_chat_room(self.chat_system.get_chat_room(data['roomid']))
                elif data['type'] == 'message':
                    if data['content'] != '' and data['content'][0] == "$":
                        if data['content'] == "$sayhello":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    try:
                                        response = self.chat_system.stubs[server_j].sayHello(
                                            route_pb2.HelloRequest(request=self.server_id))
                                    except grpc.RpcError as e:
                                        pass
                        elif data['content'] == "$betheleader":
                            for server_j in self.chat_system.servers:
                                if server_j != self.server_id:
                                    try:
                                        response = self.chat_system.stubs[server_j].leaderElection(
                                            route_pb2.LeaderElectionRequest(leader_id=self.server_id))
                                    except grpc.RpcError as e:
                                        pass

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

    def grpc_server(self):
        serverGrpc = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        route_pb2_grpc.add_serviceServicer_to_server(
            Service(self), serverGrpc)
        serverGrpc.add_insecure_port(str(self.server_address) + ':' + str(self.coordination_port))
        serverGrpc.start()
        print('grpc server starts at: ', str(self.server_address), ':', str(self.coordination_port))
        # start_new_thread(self.client_server_tcp_handler, ())
        serverGrpc.wait_for_termination()


class Service(route_pb2_grpc.serviceServicer):

    def __init__(self, current_server):
        self.current_server = current_server

    def sayHello(self, request, context):
        print("Server: " + request + " said hello to Server: " + self.current_server.server_id)
        return route_pb2.Response(response='OK')

    def leaderElection(self, request, context):
        self.current_server.chat_system.leader = request
        print('Server:', request, "said Server:", request, 'is the new leader')

    def identityApproval(self, request, context):
        requested_user = self.current_server.chat_system.get_user(request.client_id)
        if requested_user:
            return route_pb2.Approval(approval='false')
        else:
            if request.server_id != self.current_server.server_id:
                self.current_server.chat_system.add_user(Client(request.client_id, None,
                                                                self.current_server.chat_system.servers[
                                                                    request.server_id]))
                self.current_server.chat_system.get_user(request.client_id).room = None
            for server_i in self.current_server.chat_system.stubs.keys():
                if server_i != self.current_server.chat_system.this_server_id and server_i != request.server_id:
                    try:
                        res = self.current_server.chat_system.stubs[server_i].newIdentityByLeader(
                            route_pb2.NewIdentityRequest(client_id=request.client_id, approval='true',
                                                         server_id=request.server_id))
                    except grpc.RpcError as e:
                        print('Cannot connect to the server:', str(server_i))

                        pass

            return route_pb2.Approval(approval='true')

    def newIdentityByLeader(self, request, context):

        if request.approval == 'true':
            self.current_server.chat_system.add_user(Client(request.client_id, None,
                                                            self.current_server.chat_system.servers[request.server_id]))
            self.current_server.chat_system.get_user(request.client_id).room = None
        return route_pb2.Response(response='OK')

    def deleteIdentity(self, request, context):
        self.current_server.chat_system.delete_user(self.current_server.chat_system.get_user(request.client_id))
        return route_pb2.Response(response='OK')

    def roomApproval(self, request, context):
        requested_chat_room = self.current_server.chat_system.get_chat_room(request.room_id)  # gives False or chatroom
        if requested_chat_room:
            return route_pb2.RoomApproval(approval='false', room_id=request.room_id)
        else:
            if request.server_id != self.current_server.server_id:
                self.current_server.chat_system.add_chat_room(ChatRoom(request.room_id,
                                                                       self.current_server.chat_system.servers[
                                                                           request.server_id].owner,
                                                                       self.current_server.chat_system.servers[
                                                                           request.server_id]))
            for server_i in self.current_server.chat_system.stubs.keys():
                if server_i != self.current_server.chat_system.this_server_id and server_i != request.server_id:
                    try:
                        res = self.current_server.chat_system.stubs[server_i].createRoomByLeader(
                            route_pb2.NewRoomRequest(room_id=request.room_id, client_id=request.client_id,
                                                     server_id=request.server_id, approval='true'))
                    except grpc.RpcError as e:
                        print('Cannot connect to the server:', str(server_i))
                        pass

            return route_pb2.RoomApproval(approval='true', room_id=request.room_id)

    def createRoomByLeader(self, request, context):
        if request.approval == 'true':
            self.current_server.chat_system.add_chat_room(ChatRoom(request.room_id,
                                                                   self.current_server.chat_system.servers[
                                                                       request.server_id].owner,
                                                                   self.current_server.chat_system.servers[
                                                                       request.server_id]))

            return route_pb2.Response(response='OK')

    def deleteRoom(self, request, context):
        self.current_server.chat_system.delete_chat_room(self.current_server.chat_system.chat_rooms[request.room_id])
        return route_pb2.Response(response='OK')

    def changeServerApproval(self, request, context):
        self.current_server.chat_system.increase_vector_clock(eval(request.vector_clock))
        if request.current_server_id != self.current_server.server_id:
            requested_user = self.current_server.chat_system.get_user(request.client_id)
            requested_user.room = None
            requested_user.server = None
        self.current_server.chat_system.increase_vector_clock()

        return_res = route_pb2.ChangeServerApproval(approval='true', vector_clock=str(
            self.current_server.chat_system.get_vector_clock()))

        self.current_server.chat_system.increase_vector_clock()

        for server_i in self.current_server.chat_system.stubs.keys():
            if server_i != self.current_server.chat_system.this_server_id and server_i != request.current_server_id:
                try:
                    res = self.current_server.chat_system.stubs[server_i].changeServerByLeader(
                        route_pb2.ChangeServerRequest(current_server_id=request.current_server_id,
                                                      destination_server_id=request.destination_server_id,
                                                      client_id=request.client_id, approval='true',
                                                      vector_clock=str(
                                                          self.current_server.chat_system.get_vector_clock())))
                except grpc.RpcError as e:
                    print('Cannot connect to the server:', str(server_i))
                    pass
        print(
            "changeserver request from " + request.current_server_id + " to " + request.destination_server_id + " by " + request.client_id)
        return return_res

    def changeServerByLeader(self, request, context):
        self.current_server.chat_system.increase_vector_clock(eval(request.vector_clock))
        if self.current_server.chat_system.compare_vector_clock(eval(request.vector_clock)):
            requested_user = self.current_server.chat_system.get_user(request.client_id)
            requested_user.room = None
            requested_user.server = None
        self.current_server.chat_system.increase_vector_clock()
        return route_pb2.Response(response='OK')

    def new_leader(self, request, context):
        self.current_server.chat_system.leader = request.leader_id
        self.current_server.bully.new_leader_msg(request.sender_id)
        print("Server:", request.sender_id, "said Server:", request.leader_id, "is the new leader")
        return route_pb2.Response(response='OK')

    def start_election(self, request, context):
        self.current_server.bully.election_msg_received(request.server_id)
        return route_pb2.Response(response='OK')

    def took_over(self, request, context):
        self.current_server.bully.took_over_msg(request.server_id)
        return route_pb2.Response(response='OK')

    def delete_server(self, request, context):
        self.current_server.chat_system.servers.pop(request.server_id)
        print("server", request.server_id, "deleted from serverlist. new list =",
              str(self.current_server.chat_system.servers))
        return route_pb2.Response(response='OK')

    def is_live(self, request, context):
        return route_pb2.HeartBeatStatus(isLive='True')


# GRPC Ends ######################################################################################

class ChatSystem:
    def __init__(self):
        self.servers = {}
        self.user_list = {}
        self.chat_rooms = {}
        self.vector_clock = {}
        self.leader = None
        self.this_server_id = self.identify_servers()
        self.server = self.servers[self.this_server_id]
        self.stubs = GrpcConnections.create_stubs(self.servers)
        self.elect_leader()
        self.server.run_grpc_server()

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
            self.add_chat_room(ChatRoom("MainHall-" + a[0], server_j.owner, server_j))
            self.vector_clock[a[0]] = 0
        print(self.servers)
        return server_id

    def elect_leader(self):
        self.leader = "s1"
        try:
            self.send_to_other_servers(
                {"type": "leader_election", "leader": self.leader, "sender": self.this_server_id})
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
                    s.connect((self.servers[server_j].server_address, int(self.servers[server_j].coordination_port)))
                    s.sendall(json.dumps(payload,
                                         ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))

    def get_vector_clock(self):
        with threading.Lock():
            return self.vector_clock

    def get_leader(self):
        with threading.Lock():
            return self.leader

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


# Bully Algorithm
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
        if (self.state != "takenover"):
            self.send_elected_msg()
            self.setState("coordinator")
            print("Server " + str(self.serverid) +
                  " is elected as the new leader")
        else:
            self.setState("intermediate")
        return

    def send_election_msg(self, id):
        try:
            response = self.serverList[id].stub.start_election(route_pb2.BullyMessage(server_id=self.serverid))
        except grpc.RpcError as e:
            print('Cannot connect to:', self.serverList[id].server_address, self.serverList[id].coordination_port)
            pass

    def send_elected_msg(self):
        for i in self.serverList:
            try:
                response = self.serverList[i].stub.new_leader(
                    route_pb2.NewLeaderMessage(sender_id=self.serverid, leader_id=self.serverid))
            except grpc.RpcError as e:
                print('Cannot connect to:', self.serverList[i].server_address, self.serverList[i].coordination_port)
                pass

    def new_leader_msg(self, id):
        print("")
        self.setState("coordinated")

    def took_over_msg(self, id):
        self.setState("takenover")

    def election_msg_received(self, id):
        self.setState("takenover")
        print(self.serverid + " received election msg from " + id)
        try:
            response = self.serverList[id].stub.took_over(route_pb2.BullyMessage(server_id=self.serverid))
        except grpc.RpcError as e:
            print('Cannot connect to:', self.serverList[id].server_address, self.serverList[id].coordination_port)
            pass
        if (self.getState != "election" and self.getState != "takenover"):
            self.run_election()


chat_system = ChatSystem()

# python 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\server.py' -server_id s1 -servers_conf "C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\servers_conf.txt"

# java -jar 'C:\Users\thisa\Desktop\Sem 7\Distributed Systems\project\DistributedSystemsProject\client.jar' -h 127.0.0.1 -p 4444 -i Adel1
