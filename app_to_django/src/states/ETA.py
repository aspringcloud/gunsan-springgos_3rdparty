#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
import json
import GPSeuclidean
import time
# Rest API server 주소
BASEURL = 'https://test.aspringcloud.com/api'

# Rest API Basic auth 인증을 위한 계정 정보
BasicAuth_id = 'cgchae@aspringcloud.com'
BasicAuth_password = '0220Know'

# 이 프로그램이 수행하는 기능은 총 2가지로 구성됨
# 1. 스테이션 A,B 간의 예상 이동 시간.
# 2. 각 스테이션별 차량의 예상 도착 시간을 저장

# DB는 외부로 이동 될수 있으므로, 하나의 특정 서버를 지정하여 구성.
# 각 Site별 Stations api 에서 제공하는 [sta_Order] Column의 데이터를 사용.
StationDistEachSite = {
        # 군산
        1 : {12: 451, 13: 451, 11: 915, 18: 664, 9: 10, 19: 664, 10: 915},
        # 대구
        2 : {1: 915, 2: 540, 3: 880, 4: 932}
    }

def GetStationInfo():
    global BASEURL, BasicAuth_id, BasicAuth_password

    # 각 스테이션 별 순서 및 거리를 계산 하기 위한 dict 형 변수
    """
    # data format 
    { [site ID]:{  [스테이션 순번] :  { 'distance To Next':
                                    'station Id' :
                                   }      
    """
    StationInfo = {}
    StationGPS = {}
    """
    각 사이트별 스테이션 간의 거리를 나타내는 dict 형 변수
    """
    StationDistance = {}
    URL = '/stations'

    # 각 스테이션 별 거리 정보
    res = requests.get(BASEURL + URL, auth=(BasicAuth_id, BasicAuth_password))
    Station_Data = json.loads(res.text)

    # 전반적인 형태의 데이터 구성
    for sta_index in Station_Data:
        if sta_index['site'] not in StationInfo:
            StationInfo.setdefault(sta_index['site'], {})

        if sta_index['sta_Order'] not in StationInfo[sta_index['site']]:

            if sta_index['sta_Order'] != None and sta_index['sta_Order'].isdigit() == True:
                order = int(sta_index['sta_Order'])
            else:
                order = sta_index['sta_Order']

            StationInfo[sta_index['site']].setdefault(order, {})

        StationInfo[sta_index['site']][order] = {'station_Id': sta_index['id'], 'eta': sta_index['eta']}
        StationGPS.setdefault( sta_index['id'], {'lat': sta_index['lat'], 'lon': sta_index['lon']})

    return StationInfo, StationGPS
    # 다음 스테이션 까지의 거리 계산 수행 및 데이터 업데이트

def GetVehicleInfo():
    global BASEURL, BasicAuth_id, BasicAuth_password

    VehiclesALL_URL = '/vehicles/'

    res = requests.get(BASEURL + VehiclesALL_URL, auth=(BasicAuth_id, BasicAuth_password))
    info = json.loads(res.text)

    VehicleList = {}
    Site2Vehicles = {}
    for vehicleindex in info:
        # if vehicleindex['drive'] is True:
        VehicleList.setdefault(vehicleindex['id'], )
        VehicleList[vehicleindex['id']] = {
            "drive": vehicleindex['drive'],
            "mid": vehicleindex['mid'],
            'state': vehicleindex['state'],
            "site": vehicleindex['site'],
            "passed_station": vehicleindex['passed_station'],
            'wheelbase_speed': vehicleindex['wheelbase_speed'],
            'lat': vehicleindex['lat'],
            'lon': vehicleindex['lon']
        }
        # site에 소속된 Vehicle 정보 리턴
        Site2Vehicles.setdefault(vehicleindex['site'], [])
        Site2Vehicles[vehicleindex['site']].append(vehicleindex['id'])

    # Site2Vehicles의 키값은 None일수 있으며, 해당 데이터는 미 배치된  차량을 의미
    return VehicleList, Site2Vehicles

def ETA_sta2sta(StationInfo):
    global StationDistEachSite

    # 각 차량별 각각의 station에 도착하는데 걸리는 예상시간
    """
    output format
    sta2Sta_ETA = {
                        [
                         [출발지 station No.1] : {
                                        [도착지 station No.1] : [분],
                                        [도착지 station No.2] : [분],
                                            .
                                            .
                                            },
                         ,
                         [정류장 접근 순서]
                        ]
                        [
                         [출발지 station No.2] : {
                                        [도착지 station No.1-2] : [분],
                                        [도착지 station No.2-2] : [분],
                                            .
                                            .
                                            }
                         ,
                         [정류장 접근 순서]
                        ]
                    }
    """
    sta2Sta_ETA = {}
    for SiteIndex in StationDistEachSite.keys():
        indexList = list(range(1, len(StationInfo[SiteIndex]) + 1))

        SequecnIndexList = None
        for index in indexList:
            currentStation = StationInfo[SiteIndex][index]['station_Id']
            sta2Sta_ETA.setdefault(currentStation,{})

            # 각 station별 접근 순서 리스트 구성
            SequecnIndexList = indexList[index:] + indexList[: index - 1]

            EstimateTime = 0
            # 각 스테이션별 접근 수행
            temp_dict = {}
            station_sequen = []
            for nextStationIndex in SequecnIndexList:
                nextStation = StationInfo[SiteIndex][nextStationIndex]['station_Id']
                # 10은 10km/h 를 의미하며, 이는 저속 운행 시의 시간을 나타냄
                temp = round(StationDistEachSite[SiteIndex][nextStation] / ( 14 * 16.7 ) )
                if temp == 0:
                    EstimateTime += 1
                else:
                    EstimateTime += temp
                temp_dict.setdefault(nextStation, EstimateTime)
                station_sequen.append(nextStation)

            sta2Sta_ETA[currentStation] = [temp_dict, station_sequen ]

    return sta2Sta_ETA

# origin, target, vehicle 정보 모두 dict 형태의 데이터를 사용하며, lat : x, lon : y 의 형태를 사용
def CalcGPSEuclidean(origin, target, vehicle):
    origin2target = GPSeuclidean.GeoUtil.get_euclidean_distance(
                        float(target['lon']), float(target['lat']), float(origin['lon']), float(origin['lat'])
                    )

    vehicle2target = GPSeuclidean.GeoUtil.get_euclidean_distance(
                         float(origin['lon']), float(origin['lat']), float(vehicle['lon']), float(vehicle['lat'])
                    )
    if vehicle2target == 0:
        return 0
    else:
        return vehicle2target / origin2target

# 각 vehicle이 각 정류장에 도착할때 까지의 시간 계산
def EachVehicleETA(VehicleList, Site2Vehicles, sta2staETA, StationInfo, StationGPS):
    global BASEURL, BasicAuth_id, BasicAuth_password, StationDistEachSite

    # 스테이션별 각 차량 ETA 구성
    """
    Vehicle_ETA ={
                [station 1] : { 
                            [차량 번호 1]: [n분],
                            [차량 번호 2]: [n분],
                                .
                                .
                            },
                [station 2] : { 
                            [차량 번호 1-2]: [n분],
                            [차량 번호 2-2]: [n분],
                                .
                                .
                            },
                }
    """
    Vehicle_ETA = {}
    for SiteIndex in StationDistEachSite.keys():
        for VehicleIndex in Site2Vehicles[SiteIndex]:
            if VehicleList[VehicleIndex]['drive'] == False:
                continue
            # 각 차량의 시작 번호를 취득 -> 이를 이용한, 각 상황별 필요소요 시간 계산
            start_stationNo = VehicleList[VehicleIndex]['passed_station']

            if start_stationNo is None or start_stationNo == '':
                continue

            NextStation = sta2staETA[start_stationNo][1][0]
            VehiclGPS = {'lat':VehicleList[VehicleIndex]['lat'], 'lon':VehicleList[VehicleIndex]['lon']}
            weight = CalcGPSEuclidean(StationGPS[start_stationNo], StationGPS[NextStation], VehiclGPS)

            # 차량이 운행중이 아니고, 진행중이 아닐 경우, 기본 값이 출력되도록 2의 값을 삽입
            if weight > 1:
                weight = 2
            # 기준이 되는 시간
            weightTime = sta2staETA[start_stationNo][0][NextStation] * (1 - weight)

            for ETA_Index in sta2staETA[start_stationNo][0]:
                if ETA_Index not in Vehicle_ETA.keys():
                    Vehicle_ETA.setdefault(ETA_Index, {})
                Vehicle_ETA[ETA_Index].update({VehicleIndex: abs(round(sta2staETA[start_stationNo][0][ETA_Index] - weightTime, 0))})

            # 한바퀴 돌아서 자신에게 도착하는 ETA 결과값 삽입
            if start_stationNo not in Vehicle_ETA.keys():
                Vehicle_ETA.setdefault(start_stationNo, {})
            Vehicle_ETA[start_stationNo].update({VehicleIndex: abs(round(sta2staETA[NextStation][0][start_stationNo] - weightTime, 0))})
    # ETA data가 존재하지 않는 사이트가 있을 경우
    for stationIndex in sta2staETA.keys():
        if stationIndex not in Vehicle_ETA.keys() :
            Vehicle_ETA.setdefault(stationIndex, {})
    return Vehicle_ETA

def CalcETA():
    start_time = time.time()
    StationInfo, StationGPS = GetStationInfo()
    VehicleList, Site2Vehicles = GetVehicleInfo()

    # 각 정류장별 예상 이동 소요시간 계산
    sta2Sta_ETA = ETA_sta2sta(StationInfo)

    # 각 정류장별 이동 예상 시간 계산
    Vehicle_ETA = EachVehicleETA(VehicleList, Site2Vehicles, sta2Sta_ETA, StationInfo, StationGPS)
    return sta2Sta_ETA, Vehicle_ETA

if __name__ == "__main__":
    sta2Sta_ETA, Vehicle_ETA = CalcETA()
    print(sta2Sta_ETA)
    print(Vehicle_ETA)