import grpc

from proto import route_pb2_grpc


class GrpcConnections:

    def create_stubs(servers):
        stubs = {}
        for k in servers.keys():
            channel = grpc.insecure_channel(str(servers[k].server_address) + ':' + str(servers[k].coordination_port))
            stub = route_pb2_grpc.serviceStub(channel)
            stubs[k] = stub
            print("stub", str(servers[k].server_address), ':', str(servers[k].coordination_port),
                  'created successfully')

        return stubs