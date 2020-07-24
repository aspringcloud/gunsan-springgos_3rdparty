#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
import json
import GPSeuclidean
import time
import random

DEBUG_MODE = True

# python3.7부터 Dict의 삽입 순서 보장.[stationNo : distance to next statioin(m)]

GUNSAN_SQUENCE_List = {12: 451, 13: 451, 11: 915, 18: 664,
                       9: 10, 19: 664, 10: 915}
DAEGU_SQUENCE_list = {1: 915, 2: 540, 3: 880, 4: 932}

BASEURL = 'https://api.aspringcloud.com/api'

id = 'cgchae@aspringcloud.com'
password = '0220Know'


def GetVehiclesAll():
    VehiclesALL_URL = '/vehicles/'
    res = requests.get(BASEURL + VehiclesALL_URL, auth=(id, password))

    info = json.loads(res.text)

    VehicleList = {}
    Site2Vehicles = {}
    for vehicleindex in info:
        if vehicleindex['drive'] is True:
            VehicleList.setdefault(vehicleindex['id'],)
            VehicleList[vehicleindex['id']] = {
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


def GetStationInfoAll():
    Station_API_URL = "/stations/"
    res = requests.get(BASEURL + Station_API_URL, auth=(id, password))

    StationInfo_temp = json.loads(res.text)

    # 각 site별 정보를 저장
    # StationInfo = {}

    # 사이트별 존재하는, kiosk의 일련번호를 저장.
    Site2Station = {}

    Sites_Position = {}
    for stationIndex in StationInfo_temp:
        # site를 기준으로, station을 구분하는 index
        Site2Station.setdefault(stationIndex['site'], [])
        Site2Station[stationIndex['site']].append(stationIndex['id'])

        Sites_Position.setdefault(stationIndex['id'], {})
        Sites_Position[stationIndex['id']].setdefault('lat', stationIndex['lat'])
        Sites_Position[stationIndex['id']].setdefault('lon', stationIndex['lon'])

    # 각 site별 데이터 로드
    return Site2Station, Sites_Position


def CalcEachStationETA(stationList, wheel_speed):
    eachETA = {}
    for stationIndex in stationList:
        if wheel_speed != 0 and wheel_speed is not None:
            eachETA.setdefault(stationIndex, round(stationList[stationIndex] / (wheel_speed * 16.7)))
        else:
            if DEBUG_MODE is True:
                eachETA.setdefault(stationIndex, round(stationList[stationIndex] / (10 * 16.7)))
            else:
                pass

        # 예상시간이 0분이 나올 경우.
        if eachETA[stationIndex] == 0:
            eachETA[stationIndex] = 1
    return eachETA


def CalcTotalETA(stationETA, vehi, StationsPos):
    route_list = list(stationETA.keys())
    route_index = route_list.index(vehi['passed_station'])

    # 경로 정보 수정
    if route_index == 0:
        suttle_route = route_list[1:] + route_list[0:1]
    else:
        suttle_route = route_list[route_index + 1:] + route_list[:route_index + 1]

    temp_eta = 0
    ETAofStation = {}
    # 순차적으로 계산 수행
    for routeNo in suttle_route:
        if vehi['passed_station'] == routeNo:
            # 1, 지나간 station, 다음 목표 station, 차량의 GPS 정보를 획득
            # 2. 다음 station 까지의 차량의 euclidean 거리 / 이전 station에서 다음 station까지의 상대거리 계산

            # 다음 station의 좌표 정보 획득
            lat, lon = StationsPos[suttle_route[0]].values()

            lat = lat.decode('utf-8').encode('utf-8')
            lon = lon.decode('utf-8').encode('utf-8')
            # 이전 스테이션의 GPS 정보 획득
            lat_passed, lon_passed = StationsPos[vehi['passed_station']].values()

            lat_passed = lat_passed.decode('utf-8').encode('utf-8')
            lon_passed = lon_passed.decode('utf-8').encode('utf-8')
            
            # 현재 차량의 GPS 정보 획득
            #lat_vehi, lon_vehi = vehi['lat'], vehi['lon']
            # Unicode to utf-8
            print("VehiNo", vehi['mid'], "lat:", vehi['lat'], " lon: ", vehi['lon'])
            
            # 차량의 gps 값이 들어오지 않았을 경우, 패스
            if not vehi['lat'] or not vehi['lon']:
                print("pass!")
                Relative_Distance = 1
            else:
                # unicode 'utf-8'로 변환
                lat_vehi = unicode(vehi['lat']).decode('utf-8').encode('utf-8')
                lon_vehi = unicode(vehi['lon']).decode('utf-8').encode('utf-8')

                # euclidean 상대 거리로 계산 시간 가중 계산            
                Relative_Distance = GPSeuclidean.GeoUtil.get_euclidean_distance(float(lon), float(lat), float(lon_vehi), float(lat_vehi))
                
            max = GPSeuclidean.GeoUtil.get_euclidean_distance(float(lon), float(lat), float(lon_passed), float(lat_passed))

            # 다음 스테이션과 차량의 gps가 일치할 경우 >> 값은 0, 연산 에러를 방지하기 위해, 1(분)을 삽입
            if Relative_Distance == 0:
                temp_eta = temp_eta + 1
            else:
                temp = stationETA[routeNo] * Relative_Distance/max
                if temp < 1:
                    temp_eta = temp_eta + 1
                else:
                    temp_eta = temp_eta + (stationETA[routeNo] * Relative_Distance/max)

        # 다음 스테이션이 아닐 경우
        else:
            temp_eta = temp_eta + stationETA[routeNo]

        ETAofStation.setdefault(route_list[route_list.index(routeNo)], temp_eta)

    return ETAofStation


# Vehicle별 ETA 시간을, Station 별 ETA 시간 형태로 변경
def Trans_VehiETA_2_StationETA(VehiETA):
    StationETA = {}
    for vehiIndex in VehiETA:
        for stationIndex in VehiETA[vehiIndex]:
            StationETA.setdefault(stationIndex, {})
            StationETA[stationIndex].setdefault(vehiIndex, VehiETA[vehiIndex][stationIndex])

    return StationETA


# 7/7일 변경된 내용, 인자값 : SiteNo, Passed_Station, GPS(lat, lon)
#                출력값 : {vehicleNo { stationNo_1 : ETA1, stationNo_2 : ETA2, ....}


# def Sites_Estiamtetime(siteNo, Passed_statiopn, lat, lon):
def Sites_Estiamtetime(siteNo, StationNo):
    print("siteNo:",siteNo, "StationNo: ", StationNo)
    global GUNSAN_SQUENCE_List, DAEGU_SQUENCE_list

    # 1. 사이트 넘버를 받는다.
    # 2. 받은 사이트 넘버를 기준으로, 각 키오스크와, 차량의 정보를 받는다.
    # 2-2, 해당 정보의 요청이 들어왈을 때 당시의 각 사이트의 차량 정보를 받아서 로드하며, 계산한다.
    # 3. 각 차량의 정보와 목적지의 GPS 정보의 eclidean 거리를 계산 상대적 거리를 계산, 이를 시간에 반영.
    # 4. 키오스크 별 예상 도착시간을 계산하여 리턴한다.

    # return [int] 아래의 경우, 각각 해당하는 에러값이 존재.
    # 1. site값 입력 에러
    # 2. Kiosk값 입력 에러
    # 3. 해당 site에 운행중인 차량 없음
    # 4.
    Site2Station, StationsPos = GetStationInfoAll()

    # 각 스테이션 별 예상 소요시간
    ETA_vehicles = {}
    if siteNo not in Site2Station.keys():
        # 존재하지 않는 site 키값 에러
        return 1

    else:
        if StationNo not in Site2Station[siteNo]:
            # 해당 site 내에 station 존재하지 않을 때 에러
            return 2
        else:
            VehiList, Site2Vehi = GetVehiclesAll()

            if siteNo not in Site2Vehi.keys():
                # 해당 site의 모든 차량이 작동중이 아닐 경우.
                return 3

            # 운행 중인 차량이 존재할 때, 해당 차량의 예상 값을 계산
            else:
                # 군산[1]에 대한 내용만 일단 처리, 추후 대구에 대한 내용도 추가 작성 및 지원
                if siteNo == 1:
                    SequenceList = GUNSAN_SQUENCE_List
                elif siteNo == 2:
                    SequenceList = DAEGU_SQUENCE_list

                for vehiindex in Site2Vehi[siteNo]:
                    eachETA = CalcEachStationETA(SequenceList, VehiList[vehiindex]['wheelbase_speed'])
                    # eachETA를 기준으로, 현재 위치를 기준으로 더하기 연산

                    if VehiList[vehiindex]['passed_station'] is not None:
                        StationETA_temp = CalcTotalETA(eachETA, VehiList[vehiindex], StationsPos)
                        ETA_vehicles.setdefault(vehiindex, StationETA_temp)
                    else:
                        if DEBUG_MODE is True:
                            VehiList[vehiindex]['passed_station'] = random.choice(Site2Station[siteNo])
                            StationETA_temp = CalcTotalETA(eachETA, VehiList[vehiindex], StationsPos)
                            ETA_vehicles.setdefault(vehiindex, StationETA_temp)
                        else:
                            pass

                if not StationETA_temp:
                    # StationETA_Temp가 모두 비었을때.
                    return 4


                # return ETA_vehicles
    if not Trans_VehiETA_2_StationETA(ETA_vehicles)[StationNo]:
        return False
    else:
        return Trans_VehiETA_2_StationETA(ETA_vehicles)[StationNo]

def ETA_sta2sta(StationIndex, siteIndex):
    global GUNSAN_SQUENCE_List, DAEGU_SQUENCE_list

    if siteIndex == 1:
        StationList = GUNSAN_SQUENCE_List
    elif siteIndex == 2:
        StationList = DAEGU_SQUENCE_list

    list_STAList = list( StationList )
    if list_STAList.index(StationIndex) != 0:
        ordered_STAList = list_STAList[list_STAList.index(StationIndex)+1:] + list_STAList[:list_STAList.index(StationIndex)]
    else:
        ordered_STAList = list_STAList[1:]

    sta2sta_ETA = {}
    sta2sta_ETA.setdefault(StationIndex, {})
    for index in ordered_STAList:
        sta2sta_ETA[StationIndex].setdefault( index, )
        sta2sta_ETA[StationIndex][index] = round(StationList[index] / (10 * 16.7))

    return sta2sta_ETA

if __name__ == '__main__':
    start = time.time()
    print(Sites_Estiamtetime(1, 9))
    print('excuteTime=',time.time() - start)