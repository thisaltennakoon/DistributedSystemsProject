import json
import socket

#servers = {'s1': ['localhost', '4444', '5555'], 's2': ['localhost', '4445', '5556'], 's3': ['localhost', '4446', '5557']}
class Bully:
    def __init__(self, id, serverList, state = ""):
        self.id = id
        self.state = state #coordinator, coodinated, offline, election
        self.serverList = serverList

    def setState(self, _state):
        self.state = _state

    def getState(self):
        return self.state
        
    def run_election(self):
        self.setState("election")
        print("started election by the server " + str(self.id) + "\n")
        for i in (self.serverList):
            if int(i) > int(self.id):
                reply = self.send_election_msg(i)
                print("Server " + str(self.id) + " sends a election message to server " + str(i) + "\n")
                reply = json.loads(reply)
                if(reply["type"] == "tookover"):
                    print("Election takeover mesaage received")
                    return
        
        self.send_elected_msg()
        self.setState("coordinator")
        print("Server " + str(self.id) +" is elected as the new leader")
        return

    def send_json_message(self,host,port,msg):
        message = json.dumps(msg, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8')
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.sendall(message)
            reply = s.recv(4096)
            s.close
        except socket.error:
            print("Error in connecting to server "+ id )
        finally:
            s.close()
        return repr(reply)

    def send_election_msg(self, id):
        return self.send_json_message(self.serverList[id][0],self.serverList[id][2],'{"type": "elect", "serverid": ' + self.id + '}')

    def send_elected_msg(self, connection): 
        for i in self.serverList:
            self.send_json_message(self.serverList[id][0],self.serverList[id][2],'{"type": "newleader", "serverid": ' + self.id + '}')



    
    # def listening_agent(self,msg):
    #     if(msg["type"] == "newleader"):
    #         self.setState("coordinated")
    #         #return(json.dumps('{"type": "accepted"}', ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
    #     elif(msg["type"] == "elect"):
    #         if(self.getState != "election"):
    #             self.run_election()
    #         #return(json.dumps('{"type": "tookover", "serverid": ' + self.id + '}', ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
    #     else:
    #         pass
    #         #return(json.dumps('{"type": "undefined"}', ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))


    











    
