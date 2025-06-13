#include "network_manager.h"
#include <iostream>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <assert.h>
#include <vector>

#include "opcode.h"
using namespace std;

NetworkManager::NetworkManager() 
{
  this->sock = -1;
  this->addr = NULL;
  this->port = -1;
}

NetworkManager::NetworkManager(const char *addr, int port)
{
  this->sock = -1;
  this->addr = addr;
  this->port = port;
}

void NetworkManager::setAddress(const char *addr)
{
  this->addr = addr;
}

const char *NetworkManager::getAddress()
{
  return this->addr;
}

void NetworkManager::setPort(int port)
{
  this->port = port;
}

int NetworkManager::getPort()
{
  return this->port;
}

int NetworkManager::init()
{
	struct sockaddr_in serv_addr;

	this->sock = socket(PF_INET, SOCK_STREAM, 0);
	if (this->sock == FAILURE)
  {
    cout << "[*] Error: socket() error" << endl;
    cout << "[*] Please try again" << endl;
    exit(1);
  }

	memset(&serv_addr, 0, sizeof(serv_addr));
	serv_addr.sin_family = AF_INET;
	serv_addr.sin_addr.s_addr = inet_addr(this->addr);
	serv_addr.sin_port = htons(this->port);

	if (connect(this->sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == FAILURE)
  {
    cout << "[*] Error: connect() error" << endl;
    cout << "[*] Please try again" << endl;
    exit(1);
  }
	
  cout << "[*] Connected to " << this->addr << ":" << this->port << endl;

  return sock;
}

// TODO: You should revise the following code
// int NetworkManager::sendData(uint8_t *data, int dlen)
// {
//   int sock, tbs, sent, offset, num, jlen;
//   unsigned char opcode;
//   uint8_t n[4];
//   uint8_t *p;

//   sock = this->sock;
//   // Example) data (processed by ProcessManager) consists of:
//   // Example) minimum temperature (1 byte) || minimum humidity (1 byte) || minimum power (2 bytes) || month (1 byte)
//   // Example) edge -> server: opcode (OPCODE_DATA, 1 byte)
//   opcode = OPCODE_DATA;
//   tbs = 1; offset = 0;
//   while (offset < tbs)
//   {
//     sent = write(sock, &opcode + offset, tbs - offset);
//     if (sent > 0)
//       offset += sent;
//   }
//   assert(offset == tbs);

//   // Example) edge -> server: temperature (1 byte) || humidity (1 byte) || power (2 bytes) || month (1 byte)
//   tbs = 5; offset = 0;
//   while (offset < tbs)
//   {
//     sent = write(sock, data + offset, tbs - offset);
//     if (sent > 0)
//       offset += sent;
//   }
//   assert(offset == tbs);

//   return 0;
// }


int NetworkManager::sendData(uint8_t *data, int dlen)
{
    int sock = this->sock;
    std::vector<uint8_t> packet;

    // 1. Opcode 먼저 넣기
    packet.push_back(OPCODE_DATA);

    // 2. TLV 데이터 구성
    std::vector<uint8_t> tlv;

    // 온도 (1 byte)
    tlv.push_back(1);           // ID
    tlv.push_back(1);           // Length
    tlv.push_back(data[0]);     // Value

    // 습도 (1 byte)
    tlv.push_back(2);
    tlv.push_back(1);
    tlv.push_back(data[1]);

    // 전력 (2 bytes) - big-endian로 넣기 (중요)
    tlv.push_back(3);
    tlv.push_back(2);
    // data[2], data[3]가 그냥 값이면 그대로 넣어도 되지만, endian 맞추는게 안전
    tlv.push_back(data[2]);  // 상위 바이트
    tlv.push_back(data[3]);  // 하위 바이트

    // 월 (1 byte)
    tlv.push_back(4);
    tlv.push_back(1);
    tlv.push_back(data[4]);

    // 3. TLV 길이 2 바이트 (big-endian)
    uint16_t tlv_len = static_cast<uint16_t>(tlv.size());
    packet.push_back((tlv_len >> 8) & 0xFF);
    packet.push_back(tlv_len & 0xFF);

    // 4. TLV 데이터 추가
    packet.insert(packet.end(), tlv.begin(), tlv.end());

    // 5. 전송 (write 반복)
    size_t offset = 0;
    size_t total = packet.size();
    while (offset < total)
    {
        ssize_t sent = write(sock, packet.data() + offset, total - offset);
        if (sent > 0)
            offset += sent;
        else {
            std::cerr << "[!] Error: Failed to send packet" << std::endl;
            return -1;
        }
    }

    return 0;
}






// TODO: Please revise or implement this function as you want. You can also remove this function if it is not needed
uint8_t NetworkManager::receiveCommand() 
{
  int sock;
  uint8_t opcode;
  uint8_t *p;

  sock = this->sock;
  opcode = OPCODE_WAIT;

  while (opcode == OPCODE_WAIT)
    read(sock, &opcode, 1);

  assert(opcode == OPCODE_DONE || opcode == OPCODE_QUIT) ;

  return opcode;
}
