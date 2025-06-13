import socket
import requests
import threading
import argparse
import logging
import json
import sys

OPCODE_DATA = 1
OPCODE_WAIT = 2
OPCODE_DONE = 3
OPCODE_QUIT = 4


def recvn(sock, n):
    """소켓에서 n 바이트를 정확히 읽어오는 함수"""
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
             # 연결 종료됨
             raise ConnectionError("Socket connection closed unexpectedly")
        buf += chunk
    return buf

class Server:
    def __init__(self, name, algorithm, dimension, index, port, caddr, cport, ntrain, ntest):
        logging.info("[*] Initializing the server module to receive data from the edge device")
        self.name = name
        self.algorithm = algorithm
        self.dimension = dimension
        self.index = index
        self.caddr = caddr
        self.cport = cport
        self.ntrain = ntrain
        self.ntest = ntest
        success = self.connecter()

        if success:
            self.port = port
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(("0.0.0.0", port))
            self.socket.listen(10)
            self.listener()

    def connecter(self):
        success = True
        self.ai = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ai.connect((self.caddr, self.cport))
        url = "http://{}:{}/{}".format(self.caddr, self.cport, self.name)
        request = {}
        request['algorithm'] = self.algorithm
        request['dimension'] = self.dimension
        request['index'] = self.index
        js = json.dumps(request)
        logging.debug("[*] To be sent to the AI module: {}".format(js))
        result = requests.post(url, json=js)
        response = json.loads(result.content)
        logging.debug("[*] Received: {}".format(response))

        if "opcode" not in response:
            logging.debug("[*] Invalid response")
            success = False
        else:
            if response["opcode"] == "failure":
                logging.error("Error happened")
                if "reason" in response:
                    logging.error("Reason: {}".format(response["reason"]))
                    logging.error("Please try again.")
                else:
                    logging.error("Reason: unknown. not specified")
                success = False
            else:
                assert response["opcode"] == "success"
                logging.info("[*] Successfully connected to the AI module")
        return success

    def listener(self):
        logging.info("[*] Server is listening on 0.0.0.0:{}".format(self.port))

        while True:
            client, info = self.socket.accept()
            logging.info("[*] Server accept the connection from {}:{}".format(info[0], info[1]))

            client_handle = threading.Thread(target=self.handler, args=(client,))
            client_handle.start()

    def send_instance(self, vlst, is_training):
        if is_training:
            url = "http://{}:{}/{}/training".format(self.caddr, self.cport, self.name)
        else:
            url = "http://{}:{}/{}/testing".format(self.caddr, self.cport, self.name)
        data = {}
        data["value"] = vlst
        req = json.dumps(data)
        response = requests.put(url, json=req)
        resp = response.json()

        if "opcode" in resp:
            if resp["opcode"] == "failure":
                logging.error("fail to send the instance to the ai module")

                if "reason" in resp:
                    logging.error(resp["reason"])
                else:
                    logging.error("unknown error")
                sys.exit(1)
        else:
            logging.error("unknown response")
            sys.exit(1)




    def parse_data(self, buf, is_training):
        i = 0
        data_dict = {}

        while i < len(buf):
            if i + 2 > len(buf):
                logging.error("Invalid TLV format: incomplete header")
                return

            fid = buf[i]
            flen = buf[i + 1]
            i += 2

            if i + flen > len(buf):
                logging.error("Invalid TLV format: value exceeds buffer")
                return

            fval = buf[i:i + flen]
            i += flen

            if flen == 1:
                value = int.from_bytes(fval, byteorder='big', signed=True)
            elif flen == 2:
                value = int.from_bytes(fval, byteorder='big', signed=False)
            else:
                logging.warning(f"Unsupported field length: {flen}")
                continue

            data_dict[fid] = value

        temp = data_dict.get(1, 0)
        humid = data_dict.get(2, 0)
        power = data_dict.get(3, 0)
        month = data_dict.get(4, 0)

        lst = [temp, humid, power, month]
        logging.info(f"[Parsed TLV] [temp, humid, power, month] = {lst}")
        self.send_instance(lst, is_training)

    def handler(self, client):
        logging.info("[*] Server starts to process the client's request")

        ntrain = self.ntrain
        url = "http://{}:{}/{}/training".format(self.caddr, self.cport, self.name)

        while True:
            try:
                # 1. opcode 1바이트 받기
                rbuf = recvn(client, 1)
            except ConnectionError:
                logging.error("Connection closed by client")
                return

            opcode = int.from_bytes(rbuf, "big")
            logging.debug("[*] opcode: {}".format(opcode))

            if opcode == OPCODE_DATA:
                logging.info("[*] data report from the edge")

                # 2. TLV 길이 2바이트 받기
                tlv_len_buf = recvn(client, 2)
                tlv_len = int.from_bytes(tlv_len_buf, "big")
                logging.debug(f"[*] TLV length: {tlv_len}")

                # 3. TLV 데이터 받기
                tlv_buf = recvn(client, tlv_len)
                logging.debug(f"[*] received TLV buf: {tlv_buf}")

                self.parse_data(tlv_buf, True)

            else:
                logging.error("[*] invalid opcode")
                sys.exit(1)

            ntrain -= 1
            if ntrain > 0:
                client.send(int.to_bytes(OPCODE_DONE, 1, "big"))
            else:
                client.send(int.to_bytes(OPCODE_WAIT, 1, "big"))
                break

        # Training POST 요청
        result = requests.post(url)
        response = json.loads(result.content)
        logging.debug("[*] return: {}".format(response["opcode"]))

        ntest = self.ntest
        url = "http://{}:{}/{}/testing".format(self.caddr, self.cport, self.name)
        opcode = OPCODE_DONE
        logging.debug("[*] send the opcode OPCODE_DONE")
        client.send(int.to_bytes(opcode, 1, "big"))

        while ntest > 0:
            try:
                rbuf = recvn(client, 1)
            except ConnectionError:
                logging.error("Connection closed by client")
                return

            opcode = int.from_bytes(rbuf, "big")
            logging.debug("[*] opcode: {}".format(opcode))

            if opcode == OPCODE_DATA:
                logging.info("[*] data report from the edge")

                # 2. TLV 길이 2바이트 받기
                tlv_len_buf = recvn(client, 2)
                tlv_len = int.from_bytes(tlv_len_buf, "big")
                logging.debug(f"[*] TLV length: {tlv_len}")

                # 3. TLV 데이터 받기
                tlv_buf = recvn(client, tlv_len)
                logging.debug(f"[*] received TLV buf: {tlv_buf}")

                self.parse_data(tlv_buf, False)

            else:
                logging.error("[*] invalid opcode")
                logging.error("[*] please try again")
                sys.exit(1)

            ntest -= 1

            if ntest > 0:
                opcode = OPCODE_DONE
                client.send(int.to_bytes(opcode, 1, "big"))
            else:
                opcode = OPCODE_QUIT
                client.send(int.to_bytes(opcode, 1, "big"))
                break

        # 결과 요청
        url = "http://{}:{}/{}/result".format(self.caddr, self.cport, self.name)
        result = requests.get(url)
        response = json.loads(result.content)
        logging.debug("response: {}".format(response))
        if "opcode" not in response:
            logging.error("invalid response from the AI module: no opcode is specified")
            logging.error("please try again")
            sys.exit(1)
        else:
            if response["opcode"] == "failure":
                logging.error("getting the result from the AI module failed")
                if "reason" in response:
                    logging.error(response["reason"])
                logging.error("please try again")
                sys.exit(1)
            elif response["opcode"] == "success":
                self.print_result(response)
            else:
                logging.error("unknown error")
                logging.error("please try again")
                sys.exit(1)













    # def parse_data(self, buf, is_training):
    #     temp = int.from_bytes(buf[0:1], byteorder="big", signed=True)
    #     humid = int.from_bytes(buf[1:2], byteorder="big", signed=True)
    #     power = int.from_bytes(buf[2:4], byteorder="big", signed=True)
    #     month = int.from_bytes(buf[4:5], byteorder="big", signed=True)

    #     lst = [temp, humid, power, month]
    #     logging.info("[temp, humid, power, month] = {}".format(lst))

    #     self.send_instance(lst, is_training)


    # TODO: You should implement your own protocol in this function
    # The following implementation is just a simple example
    # def handler(self, client):
    #     logging.info("[*] Server starts to process the client's request")

    #     ntrain = self.ntrain
    #     url = "http://{}:{}/{}/training".format(self.caddr, self.cport, self.name)

    #     while True:
    #         # opcode (1 byte): 
    #         rbuf = client.recv(1)
    #         opcode = int.from_bytes(rbuf, "big")
    #         logging.debug("[*] opcode: {}".format(opcode))

    #         if opcode == OPCODE_DATA:
    #             logging.info("[*] data report from the edge")
    #             rbuf = client.recv(5)
    #             logging.debug("[*] received buf: {}".format(rbuf))
    #             self.parse_data(rbuf, True)
    #         else:
    #             logging.error("[*] invalid opcode")
    #             logging.error("[*] please try again")
    #             sys.exit(1)

    #         ntrain -= 1

    #         if ntrain > 0:
    #             opcode = OPCODE_DONE
    #             logging.debug("[*] send the opcode OPCODE_DONE")
    #             client.send(int.to_bytes(opcode, 1, "big"))
    #         else:
    #             opcode = OPCODE_WAIT
    #             logging.debug("[*] send the opcode OPCODE_WAIT")
    #             client.send(int.to_bytes(opcode, 1, "big"))
    #             break
    
    
    # def handler(self, client):
    #     logging.info("[*] Server starts to process the client's request")

    #     ntrain = self.ntrain
    #     url = "http://{}:{}/{}/training".format(self.caddr, self.cport, self.name)

    #     while True:
    #         rbuf = client.recv(1)
    #         if not rbuf:
    #             logging.error("Connection closed by client")
    #             return
    #         opcode = int.from_bytes(rbuf, "big")
    #         logging.debug("[*] opcode: {}".format(opcode))

    #         if opcode == OPCODE_DATA:
    #             logging.info("[*] data report from the edge")

    #             # 수신: TLV 구조 → 총 12바이트 수신 (예시)
    #             rbuf = client.recv(12)
    #             logging.debug("[*] received TLV buf: {}".format(rbuf))
    #             self.parse_data(rbuf, True)
    #         else:
    #             logging.error("[*] invalid opcode")
    #             sys.exit(1)

    #         ntrain -= 1
    #         if ntrain > 0:
    #             client.send(int.to_bytes(OPCODE_DONE, 1, "big"))
    #         else:
    #             client.send(int.to_bytes(OPCODE_WAIT, 1, "big"))
    #             break

    # # 이후 training, testing, result 단계 동일...

    #     result = requests.post(url)
    #     response = json.loads(result.content)
    #     logging.debug("[*] return: {}".format(response["opcode"]))
    
    #     ntest = self.ntest
    #     url = "http://{}:{}/{}/testing".format(self.caddr, self.cport, self.name)
    #     opcode = OPCODE_DONE
    #     logging.debug("[*] send the opcode OPCODE_DONE")
    #     client.send(int.to_bytes(opcode, 1, "big"))

    #     while ntest > 0:
    #         # opcode (1 byte): 
    #         rbuf = client.recv(1)
    #         opcode = int.from_bytes(rbuf, "big")
    #         logging.debug("[*] opcode: {}".format(opcode))

    #         if opcode == OPCODE_DATA:
    #             logging.info("[*] data report from the edge")
    #             rbuf = client.recv(5)
    #             logging.debug("[*] received buf: {}".format(rbuf))
    #             self.parse_data(rbuf, False)
    #         else:
    #             logging.error("[*] invalid opcode")
    #             logging.error("[*] please try again")
    #             sys.exit(1)

    #         ntest -= 1

    #         if ntest > 0:
    #             opcode = OPCODE_DONE
    #             client.send(int.to_bytes(opcode, 1, "big"))
    #         else:
    #             opcode = OPCODE_QUIT
    #             client.send(int.to_bytes(opcode, 1, "big"))
    #             break

    #     url = "http://{}:{}/{}/result".format(self.caddr, self.cport, self.name)
    #     result = requests.get(url)
    #     response = json.loads(result.content)
    #     logging.debug("response: {}".format(response))
    #     if "opcode" not in response:
    #         logging.error("invalid response from the AI module: no opcode is specified")
    #         logging.error("please try again")
    #         sys.exit(1)
    #     else:
    #         if response["opcode"] == "failure":
    #             logging.error("getting the result from the AI module failed")
    #             if "reason" in response:
    #                 logging.error(response["reason"])
    #             logging.error("please try again")
    #             sys.exit(1)
    #         elif response["opcode"] == "success":
    #             self.print_result(response)
    #         else:
    #             logging.error("unknown error")
    #             logging.error("please try again")
    #             sys.exit(1)

    def print_result(self, result):
        logging.info("=== Result of Prediction ({}) ===".format(self.name))
        logging.info("   # of instances: {}".format(result["num"]))
        logging.debug("   sequence: {}".format(result["sequence"]))
        logging.debug("   prediction: {}".format(result["prediction"]))
        logging.info("   correct predictions: {}".format(result["correct"]))
        logging.info("   incorrect predictions: {}".format(result["incorrect"]))
        logging.info("   accuracy: {}\%".format(result["accuracy"]))

def command_line_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--algorithm", metavar="<AI algorithm to be used>", help="AI algorithm to be used", type=str, required=True)
    parser.add_argument("-d", "--dimension", metavar="<Dimension of each instance>", help="Dimension of each instance", type=int, default=1)
    parser.add_argument("-b", "--caddr", metavar="<AI module's IP address>", help="AI module's IP address", type=str, required=True)
    parser.add_argument("-c", "--cport", metavar="<AI module's listening port>", help="AI module's listening port", type=int, required=True)
    parser.add_argument("-p", "--lport", metavar="<server's listening port>", help="Server's listening port", type=int, required=True)
    parser.add_argument("-n", "--name", metavar="<model name>", help="Name of the model", type=str, default="model")
    parser.add_argument("-x", "--ntrain", metavar="<number of instances for training>", help="Number of instances for training", type=int, default=10)
    parser.add_argument("-y", "--ntest", metavar="<number of instances for testing>", help="Number of instances for testing", type=int, default=10)
    parser.add_argument("-z", "--index", metavar="<the index number for the power value>", help="Index number for the power value", type=int, default=0)
    parser.add_argument("-l", "--log", metavar="<log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)>", help="Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)", type=str, default="INFO")
    args = parser.parse_args()
    return args

def main():
    args = command_line_args()
    logging.basicConfig(level=args.log)

    if args.ntrain <= 0 or args.ntest <= 0:
        logging.error("Number of instances for training or testing should be larger than 0")
        sys.exit(1)

    Server(args.name, args.algorithm, args.dimension, args.index, args.lport, args.caddr, args.cport, args.ntrain, args.ntest)

if __name__ == "__main__":
    main()
