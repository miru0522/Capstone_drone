import { Client } from '@stomp/stompjs';
import useDroneStore from '../store/useDroneStore';
import { STATUS_TOAST, BATTERY_RTL_TOAST } from '../utils/droneStatus';
import toast from 'react-hot-toast';

let stompClient = null;
let autoFlightTimer = null; // 자동 비행 타이머

export const connectWebSocket = () => {
  // ⚠️ 이미 연결된 클라이언트가 있으면 반드시 먼저 끊는다.
  //    변수만 새 클라이언트로 덮으면 옛 클라이언트는 그대로 살아서 구독 콜백을 계속 돌린다.
  //    그러면 텔레메트리가 두 번씩 처리되어 알림이 복제된다.
  if (stompClient) {
    stompClient.deactivate();
    stompClient = null;
  }

  // SockJS를 걷어내고 네이티브 WebSocket을 쓴다.
  //
  // SockJS는 상대경로('/ws')를 받아 페이지 origin으로 해석해 줬지만,
  // @stomp/stompjs의 brokerURL은 절대 ws://·wss:// URL을 요구한다.
  // getApiBaseUrl()이 빈 문자열(same-origin)이므로 여기서 직접 조립해야 한다.
  //
  // 스킴은 페이지 프로토콜을 따라간다 — HTTPS 페이지에서 ws:// 를 쓰면
  // 브라우저가 mixed content로 차단해 대시보드가 통째로 죽는다.
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socketUrl = `${wsProtocol}//${window.location.host}/ws`;

  stompClient = new Client({
    brokerURL: socketUrl,
    debug: () => {}, // 콘솔 더러워짐 방지
    onConnect: (frame) => {
      console.log('✅ Connected to STOMP: ' + frame);

      // 1. 데이터 수신 구독
      stompClient.subscribe('/topic/telemetry', (message) => {
        if (message.body) {
          const t = JSON.parse(message.body);
          if (t.droneId) {
            const prevDrone = useDroneStore.getState().drones.find(d => d.id === t.droneId);
            const newStatus = t.status || 'ACTIVE';
            
            // 콜백 시각화: 상태(status)가 변경되었을 때 토스트 알림.
            // 문구는 utils/droneStatus 에서 관리한다 (배지 색과 같은 곳).
            if (prevDrone && prevDrone.status !== newStatus) {
              // OFFLINE에서 돌아온 것은 상태 전환이 아니라 재접속이므로 따로 알린다
              if (prevDrone.status === 'OFFLINE') {
                toast.success(`[${t.droneId}] 통신이 복구되었습니다.`);
              } else if (newStatus === 'RETURNING' && t.currentAction === 'BATTERY_RTL') {
                // 관제사가 지시하지 않은 복귀다. 일반 복귀 문구를 쓰면 자기가 누른 것으로
                // 오해하므로 사유를 밝히고, 성공이 아니라 경고로 띄운다.
                toast.error(`[${t.droneId}] ${BATTERY_RTL_TOAST}`);
              } else if (STATUS_TOAST[newStatus]) {
                toast.success(`[${t.droneId}] ${STATUS_TOAST[newStatus]}`);
              }
            }

            useDroneStore.getState().updateDroneData({
              id: t.droneId,
              // 텔레메트리 수신 시각. 이 값이 오래되면 markStaleDronesOffline이 OFFLINE으로 되돌린다.
              lastSeen: Date.now(),
              status: t.status || 'ACTIVE',
              lat: t.gps?.lat_deg || t.lat || 36.6215,
              lng: t.gps?.lon_deg || t.lng || 127.4497,
              // ?? 를 쓴다 — || 는 0을 falsy로 보고 기본값으로 덮어쓴다.
              // 착륙한 드론의 고도 0이 120m로, 방전된 배터리 0%가 100%로 표시되던 버그.
              altitude: t.altitude ?? t.gps?.abs_alt_m ?? t.gps?.alt ?? 120,
              battery: t.battery?.remaining_percent ?? (typeof t.battery === 'number' ? t.battery : 100),
              // 재개할 경로가 남아 있는가 — PAUSED일 때 "순찰 재개"/"순찰 시작"을 가른다.
              // 드론이 안 보내면(구버전·실기 미구현) true로 두어 기존 동작을 유지한다.
              hasRoute: t.hasRoute ?? true,
              currentAction: t.currentAction ?? null,
              ...(t.station && { station: t.station })
            });
          }
        }
      });

      stompClient.subscribe('/topic/events', (message) => {
        if (message.body) {
          const alertData = JSON.parse(message.body);
          useDroneStore.getState().addAlert(alertData);
          useDroneStore.getState().setAlertPanelOpen(true);
          
          // CRITICAL 또는 WARNING인 경우 모달창(화면 팝업) 띄우기 (대소문자 무관)
          if (alertData.type?.toUpperCase() === 'CRITICAL' || alertData.type?.toUpperCase() === 'WARNING') {
            useDroneStore.getState().openTTSModal(alertData.id);
          }
        }
      });

      // 드론이 현장 방송을 마쳤다는 보고. 서버가 DB에 BROADCAST_COMPLETED를 남기고
      // 이 토픽으로 알린다. 구독하지 않으면 기록만 남고 화면은 반응하지 않는다.
      stompClient.subscribe('/topic/events/status', (message) => {
        if (!message.body) return;
        try {
          const { eventId } = JSON.parse(message.body);
          if (eventId != null) useDroneStore.getState().resolveAlert(eventId);
        } catch (e) {
          console.error('방송 완료 알림 파싱 실패', e);
        }
      });

      // 임시 비행 호출 제거
    },
    // 재연결은 라이브러리가 담당한다. 여기서 connectWebSocket을 다시 부르면
    // 클라이언트가 겹쳐 쌓여 메시지가 중복 처리된다.
    reconnectDelay: 5000,
    onStompError: (frame) => {
      console.error('❌ STOMP Connection error:', frame.headers['message']);
    }
  });

  stompClient.activate();
};

export const disconnectWebSocket = () => {
  if (stompClient !== null) {
    stompClient.deactivate();
    console.log("🛑 Disconnected from STOMP");
  }
  if (autoFlightTimer) {
    clearInterval(autoFlightTimer);
  }
};

export const sendStompMessage = (destination, body) => {
  if (stompClient && stompClient.connected) {
    stompClient.publish({ destination, body: JSON.stringify(body) });
  }
};

// 임시 로직 제거됨
