import { useEffect, useState } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://192.168.1.32:8000/ws/state";

const initialSnapshot = {
  status: {
    connected: false,
    mode: "UNKNOWN",
    motor: 0,
    angle: 90,
    estop: false,
    pca: false,
    watchdog_ms: 0,
    uptime: 0,
    last_raw_line: "",
    last_update_ts: 0,
    last_ack: "",
    last_error: "",
    seq: 0,
  },
  events: [],
};

export function useWsState() {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setSnapshot(data);
      } catch (err) {
        console.error("WebSocket parse error:", err);
      }
    };

    return () => ws.close();
  }, []);

  return {
    status: snapshot.status,
    events: snapshot.events,
    wsConnected,
  };
}