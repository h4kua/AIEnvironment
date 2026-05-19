import { useEffect, useMemo, useRef, useState } from "react";

const stageTemplate = [
  { name: "PerceptionAgent", status: "DONE", timeMs: 120 },
  { name: "ReasoningAgent", status: "DONE", timeMs: 340 },
  { name: "EvaluationAgent", status: "DONE", timeMs: 210 },
  { name: "ActionAgent", status: "DONE", timeMs: 80 },
  { name: "RoutingAgent", status: "DONE", timeMs: 50 }
];

const initialDashboard = {
  riskScore: 83,
  lastRiskScore: 41,
  rainfall: 72,
  waterLevel: 0.83,
  bmkgScore: 0.74
};

const CHATBOT_RESPONSES = {
  "jakarta barat": {
    response:
      "Saat ini Jakarta Barat berada dalam kondisi siaga tinggi.\nHujan sangat deras, sekitar 72 mm/h, dan muka air Kanal Barat sudah mencapai 83% kapasitas.\nRisiko banjir dalam waktu dekat cukup besar, jadi sebaiknya hindari area rendah dan siapkan rencana evakuasi.",
    meta: "live data · Posko Banjir + BMKG",
    confidence: 0.91
  },
  "jakarta utara": {
    response:
      "Jakarta Utara saat ini perlu diwaspadai.\nHujan cukup deras, sekitar 45 mm/h, dan tinggi air di Pluit sudah berada di sekitar 67% kapasitas.\nBelum masuk kondisi darurat, tetapi warga di area pesisir sebaiknya tetap waspada dan memantau perkembangan cuaca.",
    meta: "live data · BMKG Nowcast",
    confidence: 0.78
  },
  "jakarta selatan": {
    response:
      "Untuk saat ini Jakarta Selatan masih relatif aman.\nCurah hujan rendah, sekitar 12 mm/h, dan kondisi drainase masih normal.\nBelum ada tanda kedaruratan, jadi aktivitas bisa berjalan seperti biasa sambil tetap mengikuti pembaruan cuaca.",
    meta: "live data · Posko Banjir DKI",
    confidence: 0.94
  },
  "jakarta timur": {
    response:
      "Jakarta Timur sedang berada pada level waspada.\nHujan cukup intens dan beberapa area seperti Cipinang serta Jatinegara perlu dipantau lebih dekat.\nKalau tinggal di titik rawan, ada baiknya mulai menyiapkan tas darurat dan dokumen penting.",
    meta: "live data · BMKG + OpenWeather",
    confidence: 0.76
  },
  "jakarta pusat": {
    response:
      "Jakarta Pusat saat ini dalam kondisi aman.\nHujan ringan, sekitar 8 mm/h, dan sistem drainase masih berfungsi normal.\nBelum ada indikasi risiko banjir yang berarti, jadi aktivitas harian bisa dilanjutkan seperti biasa.",
    meta: "live data · OpenWeather API",
    confidence: 0.96
  },
  tambora: {
    response:
      "Tambora saat ini termasuk area paling berisiko di Jakarta Barat.\nSkor risikonya sekitar 91%, jadi kondisinya tidak aman untuk diabaikan.\nKalau Anda berada di area rendah atau rawan genangan, sebaiknya segera bersiap menuju shelter terdekat seperti GOR Otista yang berjarak sekitar 0,8 km.",
    meta: "predictive model · conf: 0.91",
    confidence: 0.91
  },
  "curah hujan": {
    response:
      "Berikut gambaran curah hujan saat ini:\n• Jakarta Barat: 72 mm/h, sangat deras dan perlu perhatian khusus.\n• Jakarta Utara: 45 mm/h, cukup tinggi.\n• Jakarta Selatan: 12 mm/h, masih normal.\n• Jakarta Timur: 38 mm/h, sedang hingga tinggi.\n• Jakarta Pusat: 8 mm/h, ringan.\nWilayah yang paling perlu diawasi saat ini adalah Jakarta Barat.",
    meta: "OpenWeather API · diperbarui 2 menit lalu",
    confidence: 0.99
  },
  shelter: {
    response:
      "Titik evakuasi terdekat di Jakarta Barat yang bisa dipertimbangkan saat ini adalah:\n1. GOR Otista, sekitar 0,8 km, kapasitas 2.400 orang.\n2. SDN Palmerah 03, sekitar 1,2 km, kapasitas 800 orang.\n3. Masjid Al-Mubarok, sekitar 1,9 km, kapasitas 1.200 orang.\nSemua titik ini saat ini terdata aktif dan siap digunakan.",
    meta: "BPBD DKI Jakarta · verified",
    confidence: 0.98
  },
  bmkg: {
    response:
      "Peringatan BMKG terbaru menunjukkan cuaca buruk berpotensi berdampak serius di Jakarta bagian barat dan utara.\nStatus keparahan sudah masuk kategori tinggi, dengan tingkat keyakinan yang juga kuat.\nAlert ini berlaku sampai sekitar pukul 18.00 WIB, jadi wilayah terdampak sebaiknya tetap siaga sampai kondisi mereda.",
    meta: "BMKG Nowcast · CAP protocol",
    confidence: 0.95
  },
  aman: {
    response:
      "Kalau dilihat dari kondisi saat ini, area yang relatif aman adalah Jakarta Selatan dan Jakarta Pusat.\nJakarta Utara serta Jakarta Timur masih perlu diwaspadai.\nSementara itu, area dengan risiko tertinggi ada di Jakarta Barat, terutama sekitar Tambora, Palmerah, dan Kembangan.\nKalau ingin bergerak, utamakan menuju zona yang lebih tinggi dan jauh dari titik genangan.",
    meta: "pipeline run · 5 agents · 0.8s",
    confidence: 0.89
  },
  default: {
    response:
      "Maaf, saya belum menemukan jawaban yang spesifik untuk pertanyaan itu.\nCoba tanya dengan format yang lebih langsung, misalnya:\n• Status banjir Jakarta Barat\n• Curah hujan sekarang\n• Shelter terdekat\n• Apakah Tambora aman?\nSaya bisa membantu menjelaskan kondisi banjir di wilayah DKI Jakarta dengan bahasa yang lebih sederhana.",
    meta: "deFlood Assistant · powered by agentic pipeline",
    confidence: null
  }
};

const initialMessages = [
  {
    role: "user",
    text: "Status banjir Jakarta Barat sekarang?"
  },
  {
    role: "assistant",
    text:
      "Saat ini Jakarta Barat sedang dalam kondisi siaga tinggi.\nHujan sangat deras, sekitar 72 mm/h, dan muka air Kanal Barat sudah mencapai 83% kapasitas.\nArtinya risiko banjir dalam waktu dekat cukup besar, jadi warga sebaiknya mulai waspada dan menyiapkan langkah antisipasi.",
    meta: "14:23 · live data · source: Posko Banjir + BMKG",
    confidence: 0.91
  },
  {
    role: "user",
    text: "Apakah Tambora aman?"
  },
  {
    role: "assistant",
    text:
      "Untuk saat ini Tambora belum aman.\nWilayah ini punya risiko paling tinggi di Jakarta Barat, sekitar 91%.\nKalau Anda berada di area rawan atau dataran rendah, sebaiknya segera bersiap menuju shelter terdekat seperti GOR Otista, sekitar 0,8 km dari lokasi terdampak.",
    meta: "14:24 · predictive model · conf: 0.91",
    confidence: 0.91
  }
];

const quickReplySets = [
  ["status Jakarta Utara", "curah hujan sekarang", "shelter terdekat"],
  ["status Jakarta Selatan", "alert BMKG", "Tambora aman?"]
];

const pad = (value) => String(value).padStart(2, "0");

const getNowWIB = () => {
  const now = new Date();
  return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} WIB`;
};

const getRiskMode = (score) => {
  if (score >= 85) {
    return { level: "CRITICAL", live: "SIAGA-1 · LIVE", className: "danger" };
  }
  if (score >= 70) {
    return { level: "HIGH RISK", live: "HIGH RISK · LIVE", className: "danger" };
  }
  if (score >= 45) {
    return { level: "WARNING", live: "WASPADA · LIVE", className: "warning" };
  }
  return { level: "SAFE", live: "AMAN · LIVE", className: "safe" };
};

const randomBetween = (min, max, decimals = 0) => {
  const raw = min + Math.random() * (max - min);
  return Number(raw.toFixed(decimals));
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const AGENTIC_API_KEY = import.meta.env.VITE_AGENTIC_API_KEY ?? "";

const LOCATION_KEYWORDS = [
  { keyword: "jakarta barat", location: "Jakarta Barat" },
  { keyword: "jakarta utara", location: "Jakarta Utara" },
  { keyword: "jakarta selatan", location: "Jakarta Selatan" },
  { keyword: "jakarta timur", location: "Jakarta Timur" },
  { keyword: "jakarta pusat", location: "Jakarta Pusat" },
  { keyword: "tambora", location: "Jakarta Barat" },
];

const inferLocationFromQuery = (input) => {
  const normalized = input.toLowerCase();
  for (const entry of LOCATION_KEYWORDS) {
    if (normalized.includes(entry.keyword)) {
      return entry.location;
    }
  }
  return "Jakarta Barat";
};

const getResponse = (input) => {
  const normalized = input.toLowerCase();
  const entries = Object.entries(CHATBOT_RESPONSES);
  for (let index = 0; index < entries.length; index += 1) {
    const [keyword, data] = entries[index];
    if (keyword !== "default" && normalized.includes(keyword)) {
      return data;
    }
  }
  return CHATBOT_RESPONSES.default;
};

const buildAgenticSnapshot = (location, state) => ({
  fetched_at_utc: new Date().toISOString(),
  location,
  openweather: {
    main: {
      temp: 27.6,
      humidity: 86,
    },
    rain: {
      "1h": Number(state.rainfall.toFixed(0)),
    },
    coord: {
      lat: -6.2,
      lon: 106.8,
    },
  },
  poskobanjir: [
    {
      wilayah: location,
      tinggi_air: Number((state.waterLevel * 100).toFixed(0)),
      status:
        state.riskScore >= 85
          ? "Siaga 1"
          : state.riskScore >= 70
          ? "Siaga 2"
          : "Siaga 3",
    },
  ],
  bmkg_alerts: [
    {
      headline: `Hujan ${state.rainfall >= 50 ? "deras" : "sedang"} di ${location}`,
      severity: state.bmkgScore >= 0.7 ? "Severe" : "Moderate",
      certainty: "Observed",
      urgency: "Immediate",
    },
  ],
});

const fetchAgenticExplanation = async (query, state) => {
  const location = inferLocationFromQuery(query);
  const payload = buildAgenticSnapshot(location, state);

  try {
    const response = await fetch(`${API_BASE_URL}/predict/agentic/explain`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": AGENTIC_API_KEY,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let detail = `${response.status}`;
      try {
        const errBody = await response.json();
        if (errBody?.detail) detail = `${response.status} · ${errBody.detail}`;
      } catch (_) {
        /* response body is not JSON, fall back to status code */
      }
      return { error: `Backend agentic AI menolak permintaan (${detail}).` };
    }

    const data = await response.json();
    if (!data.penjelasan_ai) {
      return { error: "Backend mengembalikan respons kosong dari Claude." };
    }

    const tech = data.data_teknis || {};
    const metaBits = ["agentic AI (Claude)", location];
    if (tech.risk_level) metaBits.push(`risk: ${tech.risk_level}`);
    if (tech.district) metaBits.push(tech.district);
    if (typeof tech.execution_ms === "number" && tech.execution_ms > 0) {
      metaBits.push(`${Math.round(tech.execution_ms)}ms`);
    }

    return {
      response: data.penjelasan_ai,
      meta: metaBits.join(" · "),
      confidence: typeof tech.confidence_score === "number" ? tech.confidence_score : null,
    };
  } catch (error) {
    return {
      error: `Tidak dapat menjangkau backend agentic AI di ${API_BASE_URL}. Pastikan FastAPI berjalan dan CORS mengizinkan origin ini.`,
    };
  }
};

const getAlertBody = (waterLevel) =>
  `Posko Banjir: muka air kritis di Kanal Barat. Threshold lokal di atas level ${Math.max(
    0.85,
    waterLevel
  ).toFixed(2)} sedang menekan kapasitas drainase.`;

export default function App() {
  const [dashboardState, setDashboardState] = useState(initialDashboard);
  const [stageState, setStageState] = useState(
    stageTemplate.map((stage) => ({ ...stage }))
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [quickReplyIndex, setQuickReplyIndex] = useState(0);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatText, setChatText] = useState("");
  const [ingestVisibility, setIngestVisibility] = useState([true, true, true]);
  const [nearbyAlerts, setNearbyAlerts] = useState([
    { label: "Critical", score: 91, distance: "0.8 km" },
    { label: "High", score: 78, distance: "1.4 km" },
    { label: "High", score: 74, distance: "2.1 km" }
  ]);
  const [lastRunValue, setLastRunValue] = useState(getNowWIB());
  const [visibleSections, setVisibleSections] = useState({});
  const [isSending, setIsSending] = useState(false);
  const [evacFlash, setEvacFlash] = useState(false);
  const [backendOnline, setBackendOnline] = useState(null);
  const chatScrollRef = useRef(null);
  const timeouts = useRef([]);

  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/healthz`, { method: "GET" });
        if (!cancelled) setBackendOnline(res.ok);
      } catch (_) {
        if (!cancelled) setBackendOnline(false);
      }
    };
    ping();
    const interval = setInterval(ping, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const timers = [];
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, header: true })), 100)
    );
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, titleBar: true })), 180)
    );
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, frameOne: true })), 340)
    );
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, frameTwo: true })), 540)
    );
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, frameThree: true })), 740)
    );
    timers.push(
      setTimeout(() => setVisibleSections((prev) => ({ ...prev, architecture: true })), 960)
    );

    timeouts.current.push(...timers);
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const bootTimers = initialMessages.map((message, index) =>
      setTimeout(() => {
        setChatMessages((prev) => [...prev, message]);
      }, index * 300)
    );

    timeouts.current.push(...bootTimers);
    return () => bootTimers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatMessages, isSending]);

  const riskMode = useMemo(
    () => getRiskMode(dashboardState.riskScore),
    [dashboardState.riskScore]
  );

  const bmkgLabel = useMemo(() => {
    if (dashboardState.bmkgScore >= 0.7) return "EXTREME";
    if (dashboardState.bmkgScore >= 0.5) return "ELEVATED";
    return "NORMAL";
  }, [dashboardState.bmkgScore]);

  const alertHeadline = useMemo(
    () => `Curah hujan ekstrem — ${Math.round(dashboardState.rainfall)} mm/h`,
    [dashboardState.rainfall]
  );

  const alertBody = useMemo(
    () => getAlertBody(dashboardState.waterLevel),
    [dashboardState.waterLevel]
  );

  const refreshNearbyAlerts = () => {
    setNearbyAlerts([
      {
        label: "Critical",
        score: randomBetween(88, 93, 0),
        distance: `${randomBetween(0.7, 0.9, 1).toFixed(1)} km`
      },
      {
        label: "High",
        score: randomBetween(75, 82, 0),
        distance: `${randomBetween(1.2, 1.6, 1).toFixed(1)} km`
      },
      {
        label: "High",
        score: randomBetween(71, 78, 0),
        distance: `${randomBetween(1.9, 2.3, 1).toFixed(1)} km`
      }
    ]);
  };

  const runIngestSequence = () =>
    new Promise((resolve) => {
      setIngestVisibility([false, false, false]);
      const timers = [0, 1, 2].map((index) =>
        setTimeout(() => {
          setIngestVisibility((prev) => {
            const next = [...prev];
            next[index] = true;
            return next;
          });
          if (index === 2) {
            timeouts.current.push(
              setTimeout(resolve, 360)
            );
          }
        }, index * 400)
      );
      timeouts.current.push(...timers);
    });

  const refreshData = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    await runIngestSequence();

    setDashboardState((prev) => ({
      ...prev,
      lastRiskScore: prev.riskScore,
      riskScore: randomBetween(75, 92, 0),
      rainfall: randomBetween(60, 90, 0),
      waterLevel: randomBetween(0.78, 0.91, 2),
      bmkgScore: randomBetween(0.68, 0.82, 2)
    }));
    refreshNearbyAlerts();
    setIsRefreshing(false);
  };

  const sleep = (ms) =>
    new Promise((resolve) => {
      const timer = setTimeout(resolve, ms);
      timeouts.current.push(timer);
    });

  const runPipeline = async () => {
    if (isPipelineRunning) return;
    setIsPipelineRunning(true);
    setStageState(stageTemplate.map((stage) => ({ ...stage, status: "IDLE", timeMs: 0 })));

    for (let index = 0; index < stageTemplate.length; index += 1) {
      const targetMs = randomBetween(80, 400, 0);
      setStageState((prev) =>
        prev.map((stage, stageIndex) =>
          stageIndex === index ? { ...stage, status: "RUNNING" } : stage
        )
      );

      await new Promise((resolve) => {
        const start = performance.now();
        const frame = () => {
          const now = performance.now();
          const progress = Math.min((now - start) / 680, 1);
          const current = Math.round(targetMs * progress);
          setStageState((prevState) =>
            prevState.map((stage, stageIndex) =>
              stageIndex === index ? { ...stage, timeMs: current } : stage
            )
          );

          if (progress < 1) {
            requestAnimationFrame(frame);
          } else {
            resolve();
          }
        };
        requestAnimationFrame(frame);
      });

      setStageState((prev) =>
        prev.map((stage, stageIndex) =>
          stageIndex === index
            ? { ...stage, status: "DONE", timeMs: targetMs }
            : stage
        )
      );
      await sleep(20);
    }

    setEvacFlash(true);
    timeouts.current.push(
      setTimeout(() => {
        setEvacFlash(false);
      }, 1400)
    );
    setLastRunValue(getNowWIB());
    setIsPipelineRunning(false);
  };

  const handleSendChat = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    setChatMessages((prev) => [...prev, { role: "user", text: trimmed }]);
    setChatText("");
    setIsSending(true);

    const agenticResponse = await fetchAgenticExplanation(trimmed, dashboardState);
    const timestamp = getNowWIB().replace(" WIB", "");

    if (agenticResponse?.error) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `⚠ ${agenticResponse.error}`,
          meta: `${timestamp} · backend offline`,
          confidence: null,
        },
      ]);
    } else {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: agenticResponse.response,
          meta: `${timestamp} · ${agenticResponse.meta}`,
          confidence: agenticResponse.confidence,
        },
      ]);
    }

    setIsSending(false);
    setQuickReplyIndex((current) =>
      Math.min(current + 1, quickReplySets.length - 1)
    );
  };

  const handleQuickReply = (text) => {
    handleSendChat(text);
  };

  const answerSet = quickReplySets[
    Math.min(quickReplyIndex, quickReplySets.length - 1)
  ];

  return (
    <div className="page">
      <header
        className={`app-header fade-up ${visibleSections.header ? "visible" : ""}`}
      >
        <div className="brand-block">
          <h1 className="brand-title">
            <span className="accent">de</span>Flood.ai
          </h1>
          <p className="brand-tagline">// One AI. All Sources. Zero Delay.</p>
        </div>

        <nav className="primary-nav">
          <a className="nav-link active" href="#dashboard">Dashboard</a>
          <a className="nav-link" href="#pipeline">Pipeline</a>
          <a className="nav-link" href="#architecture">Arsitektur</a>
        </nav>

        <div className="header-right">
          <div className={`status-pill ${backendOnline === false ? "offline" : ""}`}>
            <span className="live-dot" />
            <span>
              {backendOnline === null
                ? "CHECKING BACKEND..."
                : backendOnline
                ? "AGENTIC AI ONLINE"
                : "BACKEND OFFLINE"}
            </span>
          </div>
          <div className="header-chip">Last run: {lastRunValue}</div>
          <button
            className="top-run-button"
            type="button"
            disabled={isPipelineRunning}
            onClick={runPipeline}
          >
            {isPipelineRunning ? (
              <>
                <span className="spinner" />PROCESSING...
              </>
            ) : (
              "▶ RUN PIPELINE"
            )}
          </button>
        </div>
      </header>

      <section
        className={`page-bar fade-up ${visibleSections.titleBar ? "visible" : ""}`}
        id="dashboard"
      >
        <div>
          <p className="eyebrow">// HYDRA / OPERATOR DASHBOARD</p>
          <h2>deFlood.ai — Jakarta Flood Intelligence</h2>
          <p className="page-sub">
            Realtime ingest dari Posko Banjir DKI, BMKG Nowcast, dan OpenWeather —
            diorkestrasi oleh 5-agent agentic pipeline untuk operator BPBD.
          </p>
        </div>
        <div className="tab-strip">
          <div className="tab-pill active">Realtime</div>
          <div className="tab-pill">Forecast</div>
          <div className="tab-pill">Archive</div>
        </div>
      </section>

      <section className="dashboard-grid">
        <article
          className={`panel panel-operator fade-up ${visibleSections.frameOne ? "visible" : ""}`}
        >
          <div className="panel-head">
            <span className="panel-eyebrow">// OPERATOR VIEW</span>
            <span className="panel-time">14:23 WIB</span>
          </div>
          <div className="panel-body">
            <p className="screen-kicker">// deFlood.ai / Operator View</p>
            <div className="screen-topline">
              <div className={`region-pill ${riskMode.className}`}>
                <span className="region-dot" />
                <span>Jakarta Barat</span>
              </div>
              <button
                className="refresh-button"
                type="button"
                disabled={isRefreshing}
                onClick={refreshData}
              >
                {isRefreshing ? "SYNCING..." : "REFRESH DATA"}
              </button>
            </div>

            <div className="ingest-status">
              {[
                "Fetching Posko Banjir DKI...",
                "Fetching BMKG Nowcast CAP feed...",
                "Fetching OpenWeather rainfall frame..."
              ].map((line, index) => (
                <div
                  key={line}
                  className={`ingest-line ${ingestVisibility[index] ? "visible" : ""}`}
                >
                  • {line}
                </div>
              ))}
            </div>

            <div className="risk-score-wrap">
              <div className={`risk-number ${riskMode.className}`}>
                {Math.round(dashboardState.riskScore)}
              </div>
              <div className={`risk-badge ${riskMode.className}`}>
                {riskMode.live}
              </div>
              <p className="risk-trend">
                ↑ from {Math.round(dashboardState.lastRiskScore)}% in last hour
              </p>
            </div>

            <div className="alert-card">
              <div className="alert-icon">!</div>
              <div>
                <p className={`alert-title ${riskMode.className}`}>
                  {alertHeadline}
                </p>
                <p className="alert-copy">{alertBody}</p>
                <div className="alert-link">Tap to view affected zones →</div>
              </div>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Rainfall</span>
                <span className="stat-value danger">
                  {Math.round(dashboardState.rainfall)} <small>mm/h</small>
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Water Level</span>
                <span className="stat-value danger">
                  {dashboardState.waterLevel.toFixed(2)}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">BMKG Score</span>
                <span className="stat-value danger">
                  {dashboardState.bmkgScore.toFixed(2)} <small>{bmkgLabel}</small>
                </span>
              </div>
            </div>

            <div className="section-label">Nearby Alerts</div>
            <div className="alert-list">
              {nearbyAlerts.map((alert) => (
                <div key={`${alert.label}-${alert.score}`} className="alert-row">
                  <span className="alert-dot" />
                  <div className="alert-meta">
                    <p className="alert-name">{alert.label}</p>
                    <p className="alert-sub">
                      {alert.label === "Critical" ? "Critical" : "High"} · {alert.score}% · {alert.distance}
                    </p>
                  </div>
                  <span className="alert-arrow">›</span>
                </div>
              ))}
            </div>
          </div>
        </article>

        <article
          className={`panel panel-evacuation fade-up ${visibleSections.frameTwo ? "visible" : ""}`}
          id="pipeline"
        >
          <div className="panel-head">
            <span className="panel-eyebrow">// EVACUATION & PIPELINE</span>
            <span className="panel-time">14:18 WIB</span>
          </div>
          <div className="panel-body">
            <div className={`evacuation-hero ${evacFlash ? "flash" : ""}`}>
              <div className="pulse-orb-wrap">
                <div className="pulse-ring" />
                <div className="pulse-ring-2" />
                <div className="pulse-core">!</div>
              </div>
              <div className="evac-label">SIAGA-1 · CRITICAL</div>
              <h3 className="evac-title">Evakuasi segera</h3>
              <p className="evac-copy">
                Potensi banjir di wilayah Anda dalam <strong>42 menit</strong>. Menuju
                GOR Otista (650m). Hindari Jl. Jatinegara.
              </p>
              <div className="action-stack">
                <button className="action-primary" type="button">
                  Buka rute ke titik aman
                </button>
                <button className="action-secondary" type="button">
                  Tandai diri saya aman
                </button>
                <button className="action-secondary" type="button">
                  Hubungi 112
                </button>
              </div>
            </div>

            <div className="pipeline-block">
              <div className="section-label">// AGENTIC PIPELINE — LIVE</div>
              <div className="stages">
                {stageState.map((stage) => (
                  <div key={stage.name} className={`stage-row ${stage.status.toLowerCase()}`}>
                    <span className="stage-dot" />
                    <span className="stage-name">{stage.name}</span>
                    <span className="stage-status">
                      {stage.status}
                      {stage.status === "DONE" ? " ✓" : stage.status === "RUNNING" ? " ↻" : ""}
                    </span>
                    <span className="stage-time">
                      {(stage.timeMs / 1000).toFixed(2)}s
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <button
              className="pipeline-trigger"
              type="button"
              disabled={isPipelineRunning}
              onClick={runPipeline}
            >
              {isPipelineRunning ? (
                <>
                  <span className="spinner" />PROCESSING...
                </>
              ) : (
                "▶ RUN PIPELINE"
              )}
            </button>
          </div>
        </article>

        <article
          className={`panel panel-chat fade-up ${visibleSections.frameThree ? "visible" : ""}`}
        >
          <div className="panel-head">
            <span className="panel-eyebrow">// AI ASSISTANT</span>
            <span className="panel-time">14:25 WIB</span>
          </div>
          <div className="panel-body">
            <div className="chat-header">
              <div className="ai-avatar">AI</div>
              <div>
                <h3 className="chat-title">deFlood Assistant</h3>
                <div className="chat-status">
                  <span className="online-dot" />
                  <span>online</span>
                  <span>·</span>
                  <span className="explain-chip">explainable</span>
                </div>
              </div>
            </div>

            <div className="chat-scroll" id="chatScroll" ref={chatScrollRef}>
              {chatMessages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                  <div className="bubble">
                    <pre>{message.text}</pre>
                  </div>
                  {message.meta ? (
                    <div className="message-meta">{message.meta}</div>
                  ) : null}
                  {typeof message.confidence === "number" ? (
                    <div className="confidence-wrap">
                      <div className="confidence-track">
                        <div
                          className="confidence-fill"
                          style={{ width: `${Math.round(message.confidence * 100)}%` }}
                        />
                      </div>
                      <div className="confidence-text">
                        conf {Math.round(message.confidence * 100)}%
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
              {isSending ? (
                <div className="message typing">
                  <div className="bubble">
                    <div className="typing-dots">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="quick-replies">
              {answerSet.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  className="quick-chip"
                  onClick={() => handleQuickReply(chip)}
                >
                  {chip}
                </button>
              ))}
            </div>

            <div className="chat-input-row">
              <input
                className="chat-input"
                type="text"
                placeholder="Ask anything..."
                value={chatText}
                onChange={(event) => setChatText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    handleSendChat(chatText);
                  }
                }}
                disabled={isSending}
              />
              <button
                className="chat-send"
                type="button"
                disabled={isSending}
                onClick={() => handleSendChat(chatText)}
              >
                ➤
              </button>
            </div>
          </div>
        </article>
      </section>

      <section
        className={`architecture fade-up ${visibleSections.architecture ? "visible" : ""}`}
        id="architecture"
      >
        <h3 className="architecture-title">// ARSITEKTUR TEKNIS — deFlood.ai</h3>
        <div className="arch-grid">
          <div className="arch-card">
            <span className="arch-label">Data Sources</span>
            <h4>Multi-source ingest</h4>
            <ul>
              <li>Posko Banjir DKI</li>
              <li>BMKG Nowcast (CAP/XML)</li>
              <li>OpenWeather API</li>
            </ul>
          </div>
          <div className="arch-arrow">→</div>
          <div className="arch-card">
            <span className="arch-label">Ingestion</span>
            <h4><code>poskobanjir/</code></h4>
            <p><code>main.py</code> + realtime snapshot assembly.</p>
          </div>
          <div className="arch-arrow">→</div>
          <div className="arch-card">
            <span className="arch-label">Agentic Pipeline</span>
            <h4>Perception → Reasoning → Evaluation → Action → Routing</h4>
            <p>
              XGBoost calibrated model, SHAP explainability, OOD screening, and hydrology-driven
              signal logic tuned untuk Jakarta flood operasi.
            </p>
            <p style={{ marginTop: "10px", color: "#8fe9ff", fontFamily: "JetBrains Mono, monospace" }}>
              {"16 realtime-native features · BMKG weighted threshold > 0.70 · water ratio critical > 0.85"}
            </p>
          </div>
          <div className="arch-arrow">→</div>
          <div className="arch-card">
            <span className="arch-label">API Layer</span>
            <h4>FastAPI</h4>
            <p><code>/predict/realtime-native</code> serves structured decision outputs.</p>
          </div>
        </div>
        <div className="metrics-row">
          <div className="metric-pill">✓ Accuracy: 94.4%</div>
          <div className="metric-pill">✓ AUC-ROC: 0.945</div>
          <div className="metric-pill">✓ Features: 16</div>
          <div className="metric-pill">✓ Latency: &lt;1s</div>
        </div>
      </section>

      <footer className="app-footer">
        <span>© 2026 deFlood.ai — Jakarta Flood Intelligence Operator</span>
        <span className="footer-meta">v2.0 · agentic pipeline · BPBD DKI</span>
      </footer>
    </div>
  );
}
