import grpc

import server
from proto import route_pb2_grpc, route_pb2


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
        print('user list', self.current_server.user_list)
        if request.client_id in self.current_server.user_list:

            return route_pb2.Approval(approval='false')
        else:
            self.current_server.chat_system.servers[request.client_id] = server.Client(request.client_id, None,
                                                                                       self.current_server.chat_system.servers[
                                                                                           request.server_id])
            for server_i in self.current_server.chat_system.stubs.keys():
                if server_i != self.current_server.chat_system.this_server_id:
                    res = self.current_server.chat_system.stubs[server_i].newIdentityByLeader(
                        route_pb2.NewIdentityRequest(client_id=request.client_id, approval='true',
                                                     server_id=request.server_id))
            return route_pb2.Approval(approval='true')

    def newIdentityByLeader(self, request, context):
        if request.approval == 'true':
            self.current_server.user_list[request.client_id] = server.Client(request.client_id, None,
                                                                             self.current_server.chat_system.servers[
                                                                                 request.server_id])
        return route_pb2.Response(response='OK')

    def deleteIdentity(self, request, context):
        del self.current_server.user_list[request.client_id]
        return route_pb2.Response(response='OK')

    def roomApproval(self, request, context):
        if request.room_id in self.current_server.chat_rooms:
            return route_pb2.Approval(approval='false')
        else:
            self.current_server.chat_rooms[request.room_id] = server.ChatRoom(request.room_id,
                                                                              self.current_server.chat_system.servers[
                                                                                  request.server_id].owner,
                                                                              self.current_server.chat_system.servers[
                                                                                  request.server_id])
            for server_i in self.current_server.chat_system.stubs.keys():
                if server_i != self.current_server.chat_system.this_server_id:
                    res = self.current_server.chat_system.stubs[server_i].createRoomByLeader(
                        route_pb2.NewRoomRequest(room_id=request.room_id, client_id=request.client_id,
                                                 server_id=request.server_id, approval='true'))

            return route_pb2.Approval(approval='true')

    def createRoomByLeader(self, request, context):
        if request.approval == 'true':
            self.current_server.chat_rooms[request.room_id] = server.ChatRoom(request.room_id,
                                                                              self.current_server.chat_system.servers[
                                                                                  request.server_id].owner,
                                                                              self.current_server.chat_system.servers[
                                                                                  request.server_id])

            return route_pb2.Response(response='OK')

    def deleteRoom(self, request, context):
        del self.current_server.chat_rooms[request.room_id]
        return route_pb2.Response(response='OK')

    def changeServerApproval(self, request, context):
        if request.client_id in self.current_server.user_list and request.current_server_id == \
                self.current_server.user_list[request.client_id].server.server_id:
            self.current_server.user_list[request.client_id].room = None;

            for server_i in self.current_server.chat_system.stubs.keys():
                if server_i != self.current_server.chat_system.this_server_id:
                    res = self.current_server.chat_system.stubs[server_i].changeServerByLeader(
                        route_pb2.ChangeServerRequest(current_server_id=request.room_id,
                                                      destination_server_id=request.client_id,
                                                      client_id=request.client_id, approval='true'))

                    return route_pb2.Approval(approval='true')

        else:
            return route_pb2.Approval(approval='false')

    def changeServerByLeader(self, request, context):
        self.current_server.user_list[request.client_id].room = None
