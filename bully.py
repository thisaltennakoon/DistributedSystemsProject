import json
import time

class Bully:
    def __init__(self, id, serverList, election = False, leader = False):
        self.id = id
        self.election = election
        self.leader = leader
        self.serverList = serverList
        self.takeoverState = False
        self.sendToHigherState = False

    def check_election(self):
        pass

    def run_election(self):
        self.election = True
        print("started election by the server " + str(self.id) + "\n")
        for i in (self.serverList):
            if i > self.id:
                self.send_election_msg(i)
                print("Server " + str(self.id) + " sends a election message to server " + str(i) + "\n")
                self.sendToHigherState = True
        if (self.sendToHigherState == False):
            self.leader = self.id
            self.send_elected_msg
            print("Server " + str(self.id) +" is elected as the new leader because it has the highest id\n")
            self.election = False
            return
        self.sendToHigherState = False
        time.sleep(2)
        if (self.takeoverState == True):
            print("Server " + str(self.id) +" gets out of the election\n") 
            self.takeoverState == False           
        else:
            self.send_elected_msg()
            print("Server " + str(self.id) +" is elected as the new leader because no one is responding to election msg\n")
            self.leader = self.id
            self.election = False
        return
            
    def got_takeover_msg(self, id):
        print("Server " + str(self.id) +" recieved election takeover message  by " + id + "\n")
        self.takeoverState = True


    def send_election_msg(self, id):
        #{"type": "elect", "serverid": self.id}
        pass

    def send_takeover_msg(self, id):
        #{"type": "takeover", "serverid": self.id}
        pass

    def send_elected_msg(self, connection): 
        pass       
        # try:
        #     connection.sendall(json.dumps({"type": "newleader", "serverid": self.id}, ensure_ascii=False).encode('utf8') + '\n'.encode('utf8'))
        # except(ConnectionResetError, OSError):
        #     pass

    def election_msg_recieved(self):
        self.send_takeover_msg()
        if(self.election == False):
            self.run_election()
        else:
            print("Server " + str(self.id) +" election in progress\n")
    
    def elected_msg_recieved(self):
        self.election = False









    
