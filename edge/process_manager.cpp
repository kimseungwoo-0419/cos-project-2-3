#include "process_manager.h"
#include "opcode.h"
#include "byte_op.h"
#include "setting.h"
#include <cstring>
#include <iostream>
#include <ctime>
using namespace std;

ProcessManager::ProcessManager()
{
  this->num = 0;
}

void ProcessManager::init()
{
}

// TODO: You should implement this function if you want to change the result of the aggregation
uint8_t *ProcessManager::processData(DataSet *ds, int *dlen)
{
  uint8_t *ret, *p;
  int num, len;
  HouseData *house;
  Info *info;
  TemperatureData *tdata;
  HumidityData *hdata;
  PowerData *pdata;
  char buf[BUFLEN];
  ret = (uint8_t *)malloc(BUFLEN);
  int power, tmp, min_humid, min_temp, max_temp, min_power, month, avg_temp, avg_power, sum_power, max_power;
  
  time_t ts;
  struct tm *tm;

  tdata = ds->getTemperatureData();
  hdata = ds->getHumidityData();
  num = ds->getNumHouseData();

  // Example) I will give the minimum daily temperature (1 byte), the minimum daily humidity (1 byte), 
  // the minimum power data (2 bytes), the month value (1 byte) to the network manager
  
  // Example) getting the minimum daily temperature
  tmp = (int) tdata->getValue(); // 평균 기온

  // Example) getting the minimum daily humidity
  min_temp = (int) tdata->getMin(); // 최소 기온

  max_temp = (int) tdata->getMax(); // 최고 기온


  sum_power = 0;
    for (int i=0; i<num; i++)
    {
      house = ds->getHouseData(i);
      pdata = house->getPowerData();
      sum_power += pdata->getValue();
    }
    avg_power = sum_power / num;

  max_power = -1;
  for (int i=0; i<num; i++)
  {
    house = ds->getHouseData(i);
    pdata = house->getPowerData();
    power = pdata->getValue();

    if (power > max_power)
      max_power = power;
  }



  // Example) getting the minimum power value
  // max_power = 0; // 최대 전력 소비량
  // for (int i=0; i<num; i++)
  // {
  //   house = ds->getHouseData(i);
  //   pdata = house->getPowerData();
  //   tmp = (int)pdata->getValue();

  //   if (tmp < max_power)
  //     max_power = tmp;
  // }

  // Example) getting the month value from the timestamp
  // ts = ds->getTimestamp();
  // tm = localtime(&ts);
  // month = tm->tm_mon + 1;

  // Example) initializing the memory to send to the network manager
  memset(ret, 0, BUFLEN);
  *dlen = 0;
  p = ret;

  // Example) saving the values in the memory
  VAR_TO_MEM_1BYTE_BIG_ENDIAN(tmp, p); //1바이트씩 잘라서 포인터p에 저장하고 다음 주소로 1바이트 만큼 이동. -> 1바이트만 저장하는 이유 -> 값이 256보다 작아서이다. 
  *dlen += 1;
  VAR_TO_MEM_1BYTE_BIG_ENDIAN(min_temp, p);
  *dlen += 1;
  VAR_TO_MEM_2BYTES_BIG_ENDIAN(avg_power, p);
  *dlen += 2;
  VAR_TO_MEM_1BYTE_BIG_ENDIAN(max_temp, p); // 가구수
  *dlen += 1;

  return ret;
}
