import asyncio
import logging
import requests
import urllib3
from mavsdk import System

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("telemetry_sender")

# 글로벌 상태 관리 (연결 여부 포함)
drone_state = {
    "is_connected": False,
    "lat": 0.0,
    "lon": 0.0,
    "batt_percent": 0.0,
    "batt_volt": 0.0
}

async def watch_connection(drone):
    """픽스호크와 물리적/프로토콜 통신 연결이 수립되었는지 모니터링"""
    try:
        async for state in drone.core.connection_state():
            drone_state["is_connected"] = state.is_connected
            if state.is_connected:
                logger.info("✅ 픽스호크 연결 확인 (Heartbeat 수신 중)")
            else:
                logger.warning("❌ 픽스호크 연결 끊김 (Heartbeat 미수신)")
    except Exception as e:
        logger.error(f"연결 모니터링 오류: {e}")

async def get_battery(drone):
    """배터리 데이터 수신"""
    try:
        async for battery in drone.telemetry.battery():
            pct = battery.remaining_percent
            # 9900% 방지 (0.99로 들어오면 100을 곱함)
            if pct <= 1.0:
                pct *= 100.0
            
            drone_state["batt_percent"] = round(pct, 1)
            drone_state["batt_volt"] = round(battery.voltage_v, 2)
    except Exception:
        pass

async def get_position(drone):
    """GPS 데이터 수신"""
    try:
        async for position in drone.telemetry.position():
            drone_state["lat"] = round(position.latitude_deg, 6)
            drone_state["lon"] = round(position.longitude_deg, 6)
    except Exception:
        pass

async def telemetry_loop():
    """서버 전송 및 상태 출력 루프"""
    url = "https://203.249.90.3:8080/telemetry"
    while True:
        await asyncio.sleep(1)
        
        # 1. 물리적 연결 자체가 안 된 경우
        if not drone_state["is_connected"]:
            logger.info("⏳ [하드웨어 연결 대기] 픽스호크의 Heartbeat 신호를 기다리는 중... (포트/권한 확인)")
            continue
            
        # 2. 연결은 됬으나 데이터(전압)가 아직 안 들어오는 경우
        if drone_state["batt_volt"] <= 0.0:
            logger.info("⏳ [파라미터 대기] 픽스호크와 연결되었으나 데이터가 없음 (SR0_EXT_STAT, SR0_POSITION 확인 필요)")
            continue
            
        data = {
            "sysid": "DR-01",
            "gps": {"lat_deg": drone_state["lat"], "lon_deg": drone_state["lon"]},
            "battery": {"remaining_percent": drone_state["batt_percent"]}
        }
        
        try:
            await asyncio.to_thread(requests.post, url, json=data, timeout=1.0, verify=False)
            logger.info(f"📡 [전송 성공] {drone_state['batt_percent']}% ({drone_state['batt_volt']}V) | Lat:{drone_state['lat']} Lon:{drone_state['lon']}")
        except Exception as e:
            logger.warning(f"⚠️ [서버 에러] 데이터는 정상이나 서버 전송 실패: {e}")

async def main():
    drone = System()
    logger.info("시리얼 포트 연결 시도 중...")
    await drone.connect(system_address="serial:///dev/pixhawk:115200")
    
    # 각 백그라운드 태스크 시작
    asyncio.create_task(watch_connection(drone))
    asyncio.create_task(get_battery(drone))
    asyncio.create_task(get_position(drone))
    asyncio.create_task(telemetry_loop())

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 프로세스가 종료되었습니다.")
