import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { useWsState } from "./hooks/useWsState";
import "./styles.css";

function cls(...items) {
  return items.filter(Boolean).join(" ");
}

function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function createSectorPath(cx, cy, outerR, innerR, startAngle, endAngle) {
  const startOuter = polarToCartesian(cx, cy, outerR, startAngle);
  const endOuter = polarToCartesian(cx, cy, outerR, endAngle);
  const startInner = polarToCartesian(cx, cy, innerR, startAngle);
  const endInner = polarToCartesian(cx, cy, innerR, endAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;

  return [
    `M ${startOuter.x} ${startOuter.y}`,
    `A ${outerR} ${outerR} 0 ${largeArcFlag} 1 ${endOuter.x} ${endOuter.y}`,
    `L ${endInner.x} ${endInner.y}`,
    `A ${innerR} ${innerR} 0 ${largeArcFlag} 0 ${startInner.x} ${startInner.y}`,
    "Z",
  ].join(" ");
}

function Header({ backendReady, wsConnected, status }) {
  return (
    <header className="topbar">
      <div className="topbar__left">
        <div className="eyebrow">SMART ROBOT CAR CONTROL</div>
        <h1>Jetracer Control Dashboard</h1>
        <p className="muted">
          Professional control interface for ESP32 + backend + perception + future Jetson Nano integration
        </p>
      </div>

      <div className="topbar__right">
        <div className="status-chip">
          <span>Backend</span>
          <strong className={backendReady ? "ok" : "bad"}>
            {backendReady ? "READY" : "OFFLINE"}
          </strong>
        </div>

        <div className="status-chip">
          <span>WebSocket</span>
          <strong className={wsConnected ? "ok" : "bad"}>
            {wsConnected ? "CONNECTED" : "DISCONNECTED"}
          </strong>
        </div>

        <div className="status-chip">
          <span>Serial</span>
          <strong className={status.connected ? "ok" : "bad"}>
            {status.connected ? "CONNECTED" : "DISCONNECTED"}
          </strong>
        </div>
      </div>
    </header>
  );
}

function Panel({
  title,
  subtitle,
  children,
  extra = null,
  className = "",
  bodyClassName = "",
}) {
  return (
    <section className={cls("panel", className)}>
      <div className="panel__header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {extra}
      </div>
      <div className={cls("panel__body", bodyClassName)}>{children}</div>
    </section>
  );
}

function RangeRow({ label, value, min, max, step, onChange, suffix = "" }) {
  return (
    <div className="slider-row">
      <div className="slider-row__label">
        <span>{label}</span>
        <strong>
          {value}
          {suffix}
        </strong>
      </div>

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />

      <div className="range-hints">
        <span>
          Min: {min}
          {suffix}
        </span>
        <span>
          Max: {max}
          {suffix}
        </span>
      </div>
    </div>
  );
}

function MotionControl({
  driveSpeed,
  setDriveSpeed,
  steerLeft,
  setSteerLeft,
  steerRight,
  setSteerRight,
  repeatMs,
  setRepeatMs,
}) {
  return (
    <Panel
      title="Motion Control"
      subtitle="Thiết lập nhanh thông số lái và tốc độ lặp lệnh."
      className="panel--compact panel--motion"
    >
      <div className="slider-list slider-list--compact">
        <RangeRow
          label="Drive Speed"
          value={driveSpeed}
          min={0}
          max={1023}
          step={1}
          onChange={setDriveSpeed}
        />

        <RangeRow
          label="Left Angle"
          value={steerLeft}
          min={0}
          max={90}
          step={1}
          onChange={setSteerLeft}
        />

        <RangeRow
          label="Right Angle"
          value={steerRight}
          min={90}
          max={180}
          step={1}
          onChange={setSteerRight}
        />

        <RangeRow
          label="Repeat Interval"
          value={repeatMs}
          min={50}
          max={500}
          step={10}
          onChange={setRepeatMs}
          suffix=" ms"
        />
      </div>
    </Panel>
  );
}

function DriveControlWheel({ driveSpeed, steerLeft, steerRight, repeatMs }) {
  const loopRef = useRef(null);
  const pressedKeysRef = useRef(new Set());
  const activePointersRef = useRef(new Map());
  const lastStopSentRef = useRef(false);
  const [activeSegments, setActiveSegments] = useState([]);

  const sectors = useMemo(() => {
    const cx = 200;
    const cy = 200;
    const outerR = 182;
    const innerR = 78;

    return {
      forward: createSectorPath(cx, cy, outerR, innerR, -45, 45),
      right: createSectorPath(cx, cy, outerR, innerR, 45, 135),
      backward: createSectorPath(cx, cy, outerR, innerR, 135, 225),
      left: createSectorPath(cx, cy, outerR, innerR, 225, 315),
    };
  }, []);

  const setActiveSegmentsSafe = (segments) => {
    const unique = Array.from(new Set(segments));
    setActiveSegments(unique);
  };

  const getKeyboardSegments = () => {
    const keys = pressedKeysRef.current;
    const segments = [];

    if (keys.has("w")) segments.push("forward");
    if (keys.has("s")) segments.push("backward");
    if (keys.has("a")) segments.push("left");
    if (keys.has("d")) segments.push("right");
    if (keys.has("x") || keys.has(" ")) segments.push("center");

    return segments;
  };

  const getPointerSegments = () => {
    return Array.from(new Set(activePointersRef.current.values()));
  };

  const getMergedSegments = () => {
    return Array.from(
      new Set([...getKeyboardSegments(), ...getPointerSegments()])
    );
  };

  const buildCommandFromSegments = (segments) => {
    const set = new Set(segments);

    if (set.has("center")) {
      return {
        stop: true,
        active: ["center"],
      };
    }

    let speed = 0;
    let angle = 90;
    const active = [];

    const hasForward = set.has("forward");
    const hasBackward = set.has("backward");
    const hasLeft = set.has("left");
    const hasRight = set.has("right");

    if (hasForward && !hasBackward) {
      speed = driveSpeed;
      active.push("forward");
    } else if (hasBackward && !hasForward) {
      speed = -driveSpeed;
      active.push("backward");
    }

    if (hasLeft && !hasRight) {
      angle = steerLeft;
      active.push("left");
    } else if (hasRight && !hasLeft) {
      angle = steerRight;
      active.push("right");
    }

    if (active.length === 0) {
      return {
        stop: true,
        active: [],
      };
    }

    return {
      stop: false,
      speed,
      angle,
      active,
    };
  };

  const sendStopOnce = async (segmentsForUi = []) => {
    setActiveSegmentsSafe(segmentsForUi);
    if (lastStopSentRef.current) return;

    try {
      await api.stop();
    } catch (err) {
      console.error("STOP error:", err);
    }
    lastStopSentRef.current = true;
  };

  const sendDriveCommand = async () => {
    const merged = getMergedSegments();
    const command = buildCommandFromSegments(merged);

    setActiveSegmentsSafe(command.active);

    if (command.stop) {
      await sendStopOnce(command.active);
      return;
    }

    lastStopSentRef.current = false;

    try {
      await api.setDrive(command.speed, command.angle);
    } catch (err) {
      console.error("DRIVE error:", err);
    }
  };

  const clearLoop = () => {
    if (loopRef.current) {
      clearInterval(loopRef.current);
      loopRef.current = null;
    }
  };

  const restartLoopIfNeeded = () => {
    clearLoop();

    const merged = getMergedSegments();
    if (merged.length === 0) return;

    loopRef.current = setInterval(() => {
      sendDriveCommand();
    }, repeatMs);
  };

  const syncInteraction = async () => {
    const merged = getMergedSegments();

    if (merged.length === 0) {
      clearLoop();
      await sendStopOnce([]);
      return;
    }

    await sendDriveCommand();
    restartLoopIfNeeded();
  };

  const makePointerHandlers = (segment) => ({
    onPointerDown: async (e) => {
      e.preventDefault();

      if (e.pointerType === "mouse" && e.button !== 0) return;

      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch (_) {
        // ignore
      }

      activePointersRef.current.set(e.pointerId, segment);
      await syncInteraction();
    },

    onPointerUp: async (e) => {
      e.preventDefault();
      activePointersRef.current.delete(e.pointerId);
      await syncInteraction();
    },

    onPointerCancel: async (e) => {
      e.preventDefault();
      activePointersRef.current.delete(e.pointerId);
      await syncInteraction();
    },

    onLostPointerCapture: async (e) => {
      activePointersRef.current.delete(e.pointerId);
      await syncInteraction();
    },

    onContextMenu: (e) => e.preventDefault(),
  });

  useEffect(() => {
    const relevantKeys = new Set(["w", "a", "s", "d", "x", " "]);

    const onKeyDown = async (e) => {
      const key = e.key.toLowerCase();
      if (!relevantKeys.has(key)) return;

      const tag = e.target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;

      e.preventDefault();

      const before = pressedKeysRef.current.size;
      pressedKeysRef.current.add(key);

      if (pressedKeysRef.current.size !== before) {
        await syncInteraction();
      }
    };

    const onKeyUp = async (e) => {
      const key = e.key.toLowerCase();
      if (!relevantKeys.has(key)) return;

      e.preventDefault();
      pressedKeysRef.current.delete(key);
      await syncInteraction();
    };

    const onBlur = async () => {
      pressedKeysRef.current.clear();
      activePointersRef.current.clear();
      clearLoop();
      await sendStopOnce([]);
      setActiveSegmentsSafe([]);
    };

    const onVisibilityChange = async () => {
      if (!document.hidden) return;
      pressedKeysRef.current.clear();
      activePointersRef.current.clear();
      clearLoop();
      await sendStopOnce([]);
      setActiveSegmentsSafe([]);
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      clearLoop();
    };
  }, [driveSpeed, steerLeft, steerRight, repeatMs]);

  useEffect(() => {
    const merged = getMergedSegments();
    if (merged.length > 0) {
      restartLoopIfNeeded();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repeatMs]);

  return (
    <Panel
      title="Drive Control"
      subtitle="Nhấn giữ để điều khiển. Hỗ trợ bàn phím và đa chạm trên điện thoại."
      extra={<div className="hint-badge">W / A / S / D / X</div>}
      className="panel--drive"
      bodyClassName="panel__body--drive"
    >
      <div className="drivepad-shell">
        <div className="drivepad-svg-wrap">
          <svg
            className="drivepad-svg"
            viewBox="0 0 400 400"
            role="img"
            aria-label="Drive control pad"
          >
            <defs>
              <radialGradient id="padDishFill" cx="50%" cy="42%" r="70%">
                <stop offset="0%" stopColor="#262d37" />
                <stop offset="45%" stopColor="#1b2129" />
                <stop offset="100%" stopColor="#0f141a" />
              </radialGradient>

              <linearGradient id="sectorFill" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#232a34" />
                <stop offset="50%" stopColor="#151b22" />
                <stop offset="100%" stopColor="#0d1218" />
              </linearGradient>

              <linearGradient id="sectorFillHover" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#2d3642" />
                <stop offset="50%" stopColor="#1a212a" />
                <stop offset="100%" stopColor="#10161d" />
              </linearGradient>

              <linearGradient id="sectorFillPressed" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0f1419" />
                <stop offset="100%" stopColor="#090d12" />
              </linearGradient>

              <linearGradient id="centerFill" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#2c3440" />
                <stop offset="100%" stopColor="#141a21" />
              </linearGradient>

              <linearGradient id="centerFillPressed" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0f1419" />
                <stop offset="100%" stopColor="#090d12" />
              </linearGradient>

              <filter id="padShadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="18" stdDeviation="16" floodColor="#000000" floodOpacity="0.42" />
              </filter>

              <filter id="sectorSoftShadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#000000" floodOpacity="0.25" />
              </filter>

              <filter id="sectorGlow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#58a6ff" floodOpacity="0.16" />
              </filter>

              <filter id="sectorPressedGlow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#58a6ff" floodOpacity="0.32" />
              </filter>
            </defs>

            <circle className="pad-dish" cx="200" cy="200" r="184" filter="url(#padShadow)" />
            <circle className="pad-ring pad-ring--outer" cx="200" cy="200" r="182" />
            <circle className="pad-ring pad-ring--mid" cx="200" cy="200" r="160" />
            <circle className="pad-ring pad-ring--inner" cx="200" cy="200" r="78" />

            <g
              className={cls("pad-sector-group", activeSegments.includes("forward") && "is-pressed")}
              {...makePointerHandlers("forward")}
            >
              <path d={sectors.forward} className="pad-sector-shape" />
              <text x="200" y="110" className="pad-label">Move Forward</text>
              <text x="200" y="129" className="pad-key-label">W</text>
            </g>

            <g
              className={cls("pad-sector-group", activeSegments.includes("right") && "is-pressed")}
              {...makePointerHandlers("right")}
            >
              <path d={sectors.right} className="pad-sector-shape" />
              <text x="304" y="201" className="pad-label">Turn Right</text>
              <text x="304" y="220" className="pad-key-label">D</text>
            </g>

            <g
              className={cls("pad-sector-group", activeSegments.includes("backward") && "is-pressed")}
              {...makePointerHandlers("backward")}
            >
              <path d={sectors.backward} className="pad-sector-shape" />
              <text x="200" y="309" className="pad-label">Move Backward</text>
              <text x="200" y="328" className="pad-key-label">S</text>
            </g>

            <g
              className={cls("pad-sector-group", activeSegments.includes("left") && "is-pressed")}
              {...makePointerHandlers("left")}
            >
              <path d={sectors.left} className="pad-sector-shape" />
              <text x="96" y="201" className="pad-label">Turn Left</text>
              <text x="96" y="220" className="pad-key-label">A</text>
            </g>

            <g
              className={cls("pad-center-group", activeSegments.includes("center") && "is-pressed")}
              {...makePointerHandlers("center")}
            >
              <circle cx="200" cy="200" r="72" className="pad-center-shape" />
              <text x="200" y="197" className="pad-label pad-label-center">March / Stop</text>
              <text x="200" y="217" className="pad-key-label">X</text>
            </g>
          </svg>
        </div>
      </div>
    </Panel>
  );
}

function CameraPanel() {
  const cameraSrc = `${api.baseUrl}/api/camera/mjpeg`;

  return (
    <Panel
      title="Camera Stream"
      subtitle="Luồng camera trực tiếp từ backend perception."
      extra={<div className="hint-badge">MJPEG</div>}
      className="panel--camera"
      bodyClassName="panel__body--camera"
    >
      <div className="camera-panel">
        <img className="camera-stream" src={cameraSrc} alt="Camera stream" />
      </div>
    </Panel>
  );
}

function PerceptionPanel({ status }) {
  const items = [
    {
      label: "Camera",
      value: status.camera_connected ? "CONNECTED" : "DISCONNECTED",
      tone: status.camera_connected ? "good" : "warn",
    },
    {
      label: "Camera FPS",
      value:
        typeof status.camera_fps === "number"
          ? status.camera_fps.toFixed(1)
          : "0.0",
      tone: "neutral",
    },
    {
      label: "Lane Offset",
      value: status.lane_offset ?? "-",
      tone: "neutral",
    },
    {
      label: "Lane Confidence",
      value:
        typeof status.lane_confidence === "number"
          ? status.lane_confidence.toFixed(3)
          : "0.000",
      tone: status.lane_confidence > 0.35 ? "good" : "warn",
    },
    {
      label: "Obstacle",
      value: status.obstacle_detected ? "DETECTED" : "CLEAR",
      tone: status.obstacle_detected ? "bad" : "good",
    },
    {
      label: "Rec Speed",
      value: status.recommended_speed ?? 0,
      tone: "neutral",
    },
    {
      label: "Rec Angle",
      value: status.recommended_angle ?? 90,
      tone: "neutral",
    },
    {
      label: "Assisted",
      value: status.assisted_enabled ? "ENABLED" : "DISABLED",
      tone: status.assisted_enabled ? "good" : "warn",
    },
  ];

  return (
    <Panel
      title="Perception"
      subtitle="Dữ liệu realtime từ camera và perception."
      className="panel--compact"
    >
      <div className="perception-grid">
        {items.map((item) => (
          <div className="perception-card" key={item.label}>
            <span>{item.label}</span>
            <strong className={cls("tone", item.tone)}>{item.value}</strong>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AssistedPanel({ status }) {
  const [loading, setLoading] = useState(false);

  const toggleAssisted = async () => {
    try {
      setLoading(true);
      if (status.assisted_enabled) {
        await api.disableAssisted();
      } else {
        await api.enableAssisted();
      }
    } catch (err) {
      alert(`Assisted toggle failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const setMode = async (mode) => {
    try {
      await api.setMode(mode);
    } catch (err) {
      alert(`Set mode failed: ${err.message}`);
    }
  };

  return (
    <Panel
      title="Assisted Driving"
      subtitle="Bật / tắt assisted mode và phối hợp perception."
      className="panel--compact"
    >
      <div className="button-row button-row--compact">
        <button className="ui-btn" onClick={() => setMode("MANUAL")}>
          MANUAL
        </button>
        <button className="ui-btn" onClick={() => setMode("ASSISTED")}>
          ASSISTED
        </button>
        <button className="ui-btn" onClick={() => setMode("AUTO_TEST")}>
          AUTO_TEST
        </button>
      </div>

      <div className="assisted-box">
        <div className="assisted-line">
          <span>Status</span>
          <strong className={status.assisted_enabled ? "text-good" : "text-warn"}>
            {status.assisted_enabled ? "ENABLED" : "DISABLED"}
          </strong>
        </div>

        <div className="assisted-line">
          <span>Serial</span>
          <strong className={status.connected ? "text-good" : "text-bad"}>
            {status.connected ? "CONNECTED" : "DISCONNECTED"}
          </strong>
        </div>

        <div className="assisted-line">
          <span>Recommended</span>
          <strong>
            speed={status.recommended_speed ?? 0} | angle={status.recommended_angle ?? 90}
          </strong>
        </div>
      </div>

      <div className="button-row button-row--compact">
        <button
          className={cls(
            "ui-btn",
            "ui-btn--primary",
            status.assisted_enabled && "ui-btn--danger"
          )}
          disabled={loading}
          onClick={toggleAssisted}
        >
          {loading
            ? "PROCESSING..."
            : status.assisted_enabled
              ? "DISABLE ASSISTED"
              : "ENABLE ASSISTED"}
        </button>
      </div>
    </Panel>
  );
}

function TelemetryPanel({ status, wsConnected }) {
  const telemetryItems = [
    { label: "Mode", value: status.mode },
    { label: "Motor", value: status.motor },
    { label: "Angle", value: status.angle },
    { label: "ESTOP", value: status.estop ? "TRUE" : "FALSE" },
    { label: "PCA9685", value: status.pca ? "READY" : "NOT READY" },
    { label: "Watchdog", value: `${status.watchdog_ms} ms` },
    { label: "Uptime", value: status.uptime },
    { label: "Seq", value: status.seq },
  ];

  return (
    <Panel
      title="Live Telemetry"
      subtitle={wsConnected ? "Realtime stream active" : "Realtime stream disconnected"}
      extra={
        <div className={cls("live-indicator", wsConnected && "live-indicator--on")}>
          {wsConnected ? "LIVE" : "OFFLINE"}
        </div>
      }
      className="panel--compact"
    >
      <div className="telemetry-grid">
        {telemetryItems.map((item) => (
          <div className="telemetry-card" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>

      <div className="meta-box meta-box--compact">
        <div className="meta-row">
          <span>Last ACK</span>
          <code>{status.last_ack || "-"}</code>
        </div>
        <div className="meta-row">
          <span>Last Error</span>
          <code>{status.last_error || "-"}</code>
        </div>
      </div>
    </Panel>
  );
}

function ControlPanelCombined({ telemEnabled, setTelemEnabled }) {
  const [speed, setSpeed] = useState(160);
  const [angle, setAngle] = useState(90);

  const run = async (fn) => {
    try {
      await fn();
    } catch (err) {
      alert(err.message);
    }
  };

  const toggleTelem = async () => {
    const next = !telemEnabled;
    try {
      await api.setTelem(next, 200);
      setTelemEnabled(next);
    } catch (err) {
      alert(`Telemetry failed: ${err.message}`);
    }
  };

  return (
    <Panel
      title="Manual Tuning + System"
      subtitle="Điều chỉnh motor / servo và quản lý telemetry."
      className="panel--compact"
    >
      <div className="control-combined">
        <div className="slider-list slider-list--compact slider-list--tight">
          <RangeRow
            label="Motor Speed"
            value={speed}
            min={-1023}
            max={1023}
            step={1}
            onChange={setSpeed}
          />

          <RangeRow
            label="Servo Angle"
            value={angle}
            min={0}
            max={180}
            step={1}
            onChange={setAngle}
          />
        </div>

        <div className="button-row button-row--compact">
          <button className="ui-btn" onClick={() => run(() => api.setMotor(speed))}>
            Set Motor
          </button>
          <button className="ui-btn" onClick={() => run(() => api.setServo(angle))}>
            Set Servo
          </button>
          <button className="ui-btn" onClick={() => run(() => api.setDrive(speed, angle))}>
            Set Drive
          </button>
        </div>

        <div className="combined-divider" />

        <div className="toggle-row">
          <span>Telemetry Stream</span>
          <button className={cls("toggle-btn", telemEnabled && "active")} onClick={toggleTelem}>
            {telemEnabled ? "ENABLED" : "DISABLED"}
          </button>
        </div>
      </div>
    </Panel>
  );
}

function EventConsole({ events, status }) {
  const merged = useMemo(() => {
    const extra = [];
    if (status.last_ack) extra.push({ kind: "ACK", message: status.last_ack });
    if (status.last_error) extra.push({ kind: "ERROR", message: status.last_error });
    return [...extra, ...events].slice(0, 60);
  }, [events, status.last_ack, status.last_error]);

  return (
    <Panel
      title="Event Console"
      subtitle="Nhật ký sự kiện từ backend, serial và perception."
      className="panel--events"
      bodyClassName="panel__body--events"
    >
      <div className="console-box">
        {merged.length === 0 ? (
          <div className="console-empty">No events</div>
        ) : (
          merged.map((item, idx) => (
            <div className="console-line" key={idx}>
              <span className={cls("console-tag", item.kind === "ERROR" ? "error" : "normal")}>
                {item.kind}
              </span>
              <code>{item.message}</code>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function FooterBar({ status }) {
  return (
    <footer className="footerbar">
      <div className="footerbar__left">
        <span>Mode: {status.mode}</span>
        <span>Motor: {status.motor}</span>
        <span>Angle: {status.angle}</span>
      </div>
      <div className="footerbar__right">
        <span>PCA: {status.pca ? "READY" : "NOT READY"}</span>
        <span>Watchdog: {status.watchdog_ms} ms</span>
        <span>Lane: {status.lane_offset ?? "-"}</span>
      </div>
    </footer>
  );
}

export default function App() {
  const { status, events, wsConnected } = useWsState();

  const [backendReady, setBackendReady] = useState(false);
  const [telemEnabled, setTelemEnabled] = useState(true);

  const [driveSpeed, setDriveSpeed] = useState(400);
  const [steerLeft, setSteerLeft] = useState(70);
  const [steerRight, setSteerRight] = useState(135);
  const [repeatMs, setRepeatMs] = useState(120);

  useEffect(() => {
    let mounted = true;

    async function init() {
      try {
        await api.getStatus();
        await api.setTelem(true, 200);
        if (mounted) {
          setBackendReady(true);
          setTelemEnabled(true);
        }
      } catch (err) {
        console.error("Backend init failed:", err);
      }
    }

    init();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="dashboard">
      <Header backendReady={backendReady} wsConnected={wsConnected} status={status} />

      <main className="workspace-grid">
        <section className="workspace-left">
          <MotionControl
            driveSpeed={driveSpeed}
            setDriveSpeed={setDriveSpeed}
            steerLeft={steerLeft}
            setSteerLeft={setSteerLeft}
            steerRight={steerRight}
            setSteerRight={setSteerRight}
            repeatMs={repeatMs}
            setRepeatMs={setRepeatMs}
          />

          <DriveControlWheel
            driveSpeed={driveSpeed}
            steerLeft={steerLeft}
            steerRight={steerRight}
            repeatMs={repeatMs}
          />
        </section>

        <section className="workspace-right">
          <div className="workspace-right-top">
            <CameraPanel />
            <PerceptionPanel status={status} />
          </div>

          <div className="workspace-right-bottom">
            <div className="stack-col stack-col--left">
              <AssistedPanel status={status} />
              <ControlPanelCombined
                telemEnabled={telemEnabled}
                setTelemEnabled={setTelemEnabled}
              />
            </div>

            <div className="stack-col stack-col--right">
              <TelemetryPanel status={status} wsConnected={wsConnected} />
              <EventConsole events={events} status={status} />
            </div>
          </div>
        </section>
      </main>

      <FooterBar status={status} />
    </div>
  );
}