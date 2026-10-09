import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Factory,
  FileSearch,
  Gauge,
  Pause,
  Play,
  RefreshCcw,
  Search,
  ShieldCheck,
  Upload,
  Wrench,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './styles.css';

const API = '/api';

type Asset = { id: string; name: string; kind: string; location: string; status: string; baseline_temp: number; baseline_vibration: number; baseline_pressure: number };
type Anomaly = { id: number; asset_id: string; signal: string; observed: number; expected: number; deviation: number; severity: string; risk_score: number; start_time: string; end_time: string; contributing_signals: string[]; status: string };
type Telemetry = { timestamp: string; temperature: number | null; vibration: number | null; pressure: number | null; scenario: string; is_ground_truth_anomaly: boolean };
type Investigation = { id: number; asset_id: string; anomaly_id: number | null; provider: string; created_at: string; result: InvestigationResult };
type InvestigationResult = {
  executive_summary: string;
  observed_symptoms: string[];
  evidence: string[];
  plausible_root_causes: string[];
  alternative_explanations: string[];
  diagnostic_checks: string[];
  recommended_maintenance_action: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  priority_justification: string;
  safety_precautions: string[];
  source_references: { title: string; section: string; chunk_id: number | null; excerpt: string }[];
  uncertainty: string;
  demo_mode: boolean;
};
type WorkOrder = { id: string; asset_id: string; anomaly_id: number | null; investigation_id: number | null; priority: string; assigned_role: string; recommended_action: string; safety_checks: string[]; status: string; approval_by: string | null; completion_notes: string | null };
type Dashboard = { assets: Record<string, number>; open_work_orders: number; current_anomalies: number; risk_distribution: Record<string, number>; trends: Record<string, unknown>[]; recent_investigations: Record<string, unknown>[]; alert_queue: Record<string, unknown>[] };
type AuditEvent = { id: number; entity_type: string; entity_id: string; action: string; actor: string; details: string; created_at: string };
type DocHit = { chunk_id: number; filename: string; section: string; excerpt: string; score: number };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const headers = isFormData ? options?.headers : { 'Content-Type': 'application/json', ...(options?.headers || {}) };
  const res = await fetch(`${API}${path}`, { headers, ...options });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

const unitFor = (signal: string) => ({ temperature: 'deg C', vibration: 'mm/s', pressure: 'kPa' }[signal] || '');
const formatTime = (value: string) => new Date(value).toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });

function Stat({ label, value, tone, icon: Icon }: { label: string; value: React.ReactNode; tone?: string; icon: React.ElementType }) {
  return <div className={`stat ${tone || ''}`}><Icon size={19} aria-hidden="true" /><div><span>{label}</span><strong>{value}</strong></div></div>;
}

function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <section className="panel"><header><h2>{title}</h2>{action}</header>{children}</section>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

function App() {
  const [page, setPage] = useState('dashboard');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [evaluation, setEvaluation] = useState<Record<string, unknown> | null>(null);
  const [selected, setSelected] = useState('MTR-204');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const selectedAsset = assets.find((asset) => asset.id === selected);
  const selectedAnomaly = anomalies.find((a) => a.asset_id === selected);
  const latestInvestigation = investigations.find((item) => item.asset_id === selected);

  async function load() {
    try {
      setError('');
      const [d, a, an, inv, wo, ev, au] = await Promise.all([
        request<Dashboard>('/dashboard'),
        request<Asset[]>('/assets'),
        request<Anomaly[]>('/anomalies'),
        request<Investigation[]>('/investigations'),
        request<WorkOrder[]>('/work-orders'),
        request<Record<string, unknown>>('/evaluation'),
        request<AuditEvent[]>('/audit'),
      ]);
      setDashboard(d);
      setAssets(a);
      setAnomalies(an);
      setInvestigations(inv);
      setWorkOrders(wo);
      setEvaluation(ev);
      setAudit(au);
      const assetId = selected || a[0]?.id || 'MTR-204';
      setTelemetry(await request<Telemetry[]>(`/assets/${assetId}/telemetry`));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load PlantGuard AI data.');
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!selected) return;
    request<Telemetry[]>(`/assets/${selected}/telemetry`).then(setTelemetry).catch((err: Error) => setError(err.message));
  }, [selected]);

  async function run(label: string, fn: () => Promise<unknown>, message = `${label} complete.`) {
    if (busy) return;
    setBusy(label);
    setError('');
    setSuccess('');
    try {
      await fn();
      await load();
      setSuccess(message);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setBusy('');
    }
  }

  async function createInvestigation(): Promise<Investigation | null> {
    if (busy) return null;
    setBusy('Investigating');
    setError('');
    setSuccess('');
    try {
      const inv = await request<Investigation>('/investigations', { method: 'POST', body: JSON.stringify({ asset_id: selected, anomaly_id: selectedAnomaly?.id }) });
      await load();
      setSuccess(`Investigation #${inv.id} created with ${inv.provider}.`);
      return inv;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Investigation failed');
      return null;
    } finally {
      setBusy('');
    }
  }

  async function createOrder() {
    let inv = latestInvestigation;
    if (!inv) inv = await createInvestigation() || undefined;
    if (!inv) return;
    await run('Creating work order', () => request('/work-orders', {
      method: 'POST',
      body: JSON.stringify({
        asset_id: selected,
        anomaly_id: selectedAnomaly?.id,
        investigation_id: inv.id,
        priority: inv.result.priority,
        assigned_role: 'Maintenance supervisor',
        recommended_action: inv.result.recommended_maintenance_action,
        safety_checks: inv.result.safety_precautions,
      }),
    }), 'Work order is ready for human approval.');
  }

  const tabs: [string, React.ElementType, string][] = [
    ['dashboard', Factory, 'Dashboard'],
    ['assets', Gauge, 'Assets'],
    ['investigations', FileSearch, 'Investigations'],
    ['work-orders', ClipboardCheck, 'Work Orders'],
    ['knowledge', Database, 'Knowledge'],
    ['evaluation', Activity, 'Evaluation'],
    ['demo', Play, 'Guided Demo'],
  ];
  const shellTone = dashboard?.assets?.critical ? 'criticalMode' : dashboard?.assets?.warning ? 'warningMode' : 'healthyMode';

  return <main className={shellTone}>
    <aside>
      <div className="brand"><ShieldCheck /><div><strong>PlantGuard AI</strong><span>Hacknetic Force</span></div></div>
      <nav aria-label="Primary navigation">{tabs.map(([id, Icon, label]) => <button className={page === id ? 'active' : ''} onClick={() => setPage(id)} key={id}><Icon size={18} aria-hidden="true" />{label}</button>)}</nav>
      <div className="sim"><span className="liveDot" />Simulated deterministic data<br />Local fallback unless Gemini is configured.</div>
    </aside>
    <section className="workspace">
      <header className="topbar"><div><div className="eyebrow"><span className="liveDot" />Industrial AI command center</div><h1>{tabs.find(([id]) => id === page)?.[2] || 'Dashboard'}</h1><p>Predict problems. Explain risks. Prevent avoidable downtime.</p></div><button onClick={load} disabled={!!busy} title="Refresh data"><RefreshCcw size={17} />Refresh</button></header>
      {error && <div className="error" role="alert"><AlertTriangle size={18} />{error}</div>}
      {success && <div className="notice" role="status">{success}</div>}
      {busy && <div className="notice" role="status">{busy}...</div>}
      {page === 'dashboard' && dashboard && <DashboardPage dashboard={dashboard} anomalies={anomalies} investigations={investigations} />}
      {page === 'assets' && <AssetsPage assets={assets} selected={selected} setSelected={setSelected} telemetry={telemetry} anomalies={anomalies} />}
      {page === 'investigations' && <InvestigationsPage asset={selectedAsset} anomaly={selectedAnomaly} investigations={investigations} onInvestigate={createInvestigation} />}
      {page === 'work-orders' && <WorkOrdersPage workOrders={workOrders} audit={audit} run={run} createOrder={createOrder} busy={busy} />}
      {page === 'knowledge' && <KnowledgePage audit={audit} run={run} />}
      {page === 'evaluation' && <EvaluationPage evaluation={evaluation} />}
      {page === 'demo' && <DemoPage asset={selectedAsset} anomaly={selectedAnomaly} telemetry={telemetry} investigation={latestInvestigation} orders={workOrders.filter((w) => w.asset_id === selected)} run={run} investigate={createInvestigation} createOrder={createOrder} busy={busy} />}
    </section>
  </main>;
}

function DashboardPage({ dashboard, anomalies, investigations }: { dashboard: Dashboard; anomalies: Anomaly[]; investigations: Investigation[] }) {
  const critical = dashboard.assets.critical || 0;
  const warning = dashboard.assets.warning || 0;
  const plantStatus = critical ? 'Critical assets require approval-ready action' : warning ? 'Warning conditions under investigation' : 'All monitored assets stable';
  return <div className="grid">
    <section className={`commandStrip ${critical ? 'critical' : warning ? 'warning' : 'healthy'}`}>
      <div>
        <span className="eyebrow"><span className="liveDot" />Live plant state</span>
        <h2>{plantStatus}</h2>
        <p>{dashboard.current_anomalies} anomaly windows, {dashboard.open_work_orders} open work orders, {investigations.length} investigations recorded.</p>
      </div>
      <div className="signalBars" aria-hidden="true"><span /><span /><span /><span /><span /></div>
    </section>
    <div className="stats">
      <Stat icon={Factory} label="Monitored machines" value={dashboard.assets.total} />
      <Stat icon={CheckCircle2} label="Healthy assets" value={dashboard.assets.healthy} tone="good" />
      <Stat icon={AlertTriangle} label="Current anomalies" value={dashboard.current_anomalies} tone="warn" />
      <Stat icon={Wrench} label="Open work orders" value={dashboard.open_work_orders} tone="bad" />
    </div>
    <Panel title="Plant Sensor Trend">
      {dashboard.trends.length ? <ResponsiveContainer height={260}><LineChart data={dashboard.trends}><CartesianGrid stroke="#263241" /><XAxis dataKey="timestamp" hide /><YAxis /><Tooltip /><Line type="monotone" dataKey="temperature" name="Temp (deg C)" stroke="#22d3ee" dot={false} /><Line type="monotone" dataKey="vibration" name="Vibration (mm/s)" stroke="#86efac" dot={false} /><Line type="monotone" dataKey="pressure" name="Pressure (kPa)" stroke="#fbbf24" dot={false} /></LineChart></ResponsiveContainer> : <Empty>No sensor readings available.</Empty>}
    </Panel>
    <Panel title="Risk Distribution">
      <ResponsiveContainer height={260}><BarChart data={Object.entries(dashboard.risk_distribution).map(([name, value]) => ({ name, value }))}><CartesianGrid stroke="#263241" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="value" fill="#22d3ee" /></BarChart></ResponsiveContainer>
    </Panel>
    <Panel title="Actionable Alert Queue">
      {anomalies.length ? <table><tbody>{anomalies.slice(0, 6).map((a) => <tr key={a.id}><td>{a.asset_id}</td><td>{a.signal}</td><td><span className={`pill ${a.severity}`}>{a.severity}</span></td><td>Risk {a.risk_score}</td></tr>)}</tbody></table> : <Empty>No open anomalies.</Empty>}
    </Panel>
    <Panel title="Recent AI Investigations">{investigations.length ? investigations.slice(0, 5).map((i) => <div className="row" key={i.id}><span>#{i.id} {i.asset_id}</span><span>{i.provider}</span></div>) : <Empty>No investigations yet.</Empty>}</Panel>
  </div>;
}

function AssetsPage({ assets, selected, setSelected, telemetry, anomalies }: { assets: Asset[]; selected: string; setSelected: (id: string) => void; telemetry: Telemetry[]; anomalies: Anomaly[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const filteredAssets = useMemo(() => assets.filter((asset) => {
    const text = `${asset.id} ${asset.name} ${asset.kind} ${asset.location}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (!status || asset.status === status);
  }), [assets, query, status]);
  const selectedAsset = assets.find((asset) => asset.id === selected);
  return <div className="split">
    <Panel title="Asset Registry" action={<span className="count">{filteredAssets.length} shown</span>}>
      <label className="field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search assets" /></label>
      <label className="field"><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All</option><option value="healthy">Healthy</option><option value="warning">Warning</option><option value="critical">Critical</option></select></label>
      <div className="assetList">{filteredAssets.map((a) => <button className={selected === a.id ? 'asset activeAsset' : 'asset'} onClick={() => setSelected(a.id)} key={a.id}><strong>{a.name}</strong><span>{a.id} - {a.kind}</span><span>{a.location}</span><span className={`pill ${a.status}`}>{a.status}</span></button>)}</div>
      {!filteredAssets.length && <Empty>No assets match the current filters.</Empty>}
    </Panel>
    <div className="stack">
      <Panel title="Asset Identity">{selectedAsset ? <div className="identity"><div><strong>{selectedAsset.name}</strong><span>{selectedAsset.kind} at {selectedAsset.location}</span></div><span className={`pill ${selectedAsset.status}`}>{selectedAsset.status}</span></div> : <Empty>Select an asset.</Empty>}</Panel>
      <Panel title="Telemetry Details">
        {telemetry.length ? <ResponsiveContainer height={280}><AreaChart data={telemetry}><CartesianGrid stroke="#263241" /><XAxis dataKey="timestamp" hide /><YAxis /><Tooltip /><Area dataKey="temperature" name="Temp (deg C)" stroke="#22d3ee" fill="#164e63" /><Area dataKey="vibration" name="Vibration (mm/s)" stroke="#86efac" fill="#14532d" /><Area dataKey="pressure" name="Pressure (kPa)" stroke="#fbbf24" fill="#78350f" /></AreaChart></ResponsiveContainer> : <Empty>No telemetry is available for this asset.</Empty>}
      </Panel>
      <Panel title="Anomaly Timeline"><table><tbody>{anomalies.filter((a) => a.asset_id === selected).map((a) => <tr key={a.id}><td>{formatTime(a.start_time)}</td><td>{a.signal} ({unitFor(a.signal)})</td><td>{a.observed} vs {a.expected}</td><td>{a.deviation}</td><td>Risk {a.risk_score}</td></tr>)}</tbody></table>{!anomalies.some((a) => a.asset_id === selected) && <Empty>No anomaly windows detected for this asset.</Empty>}</Panel>
    </div>
  </div>;
}

function InvestigationsPage({ asset, anomaly, investigations, onInvestigate }: { asset?: Asset; anomaly?: Anomaly; investigations: Investigation[]; onInvestigate: () => Promise<Investigation | null> }) {
  const inv = investigations.find((i) => i.asset_id === asset?.id);
  return <div className="stack">
    <Panel title="Investigation Summary" action={<button onClick={() => void onInvestigate()}><FileSearch size={17} />Investigate Asset</button>}>
      <h3>{asset?.name || 'Select an asset'}</h3>
      <p>{anomaly ? `${anomaly.signal} anomaly: observed ${anomaly.observed} ${unitFor(anomaly.signal)}, baseline ${anomaly.expected}, risk ${anomaly.risk_score}.` : 'No active anomaly selected.'}</p>
    </Panel>
    {inv ? <Panel title={`Evidence-Grounded Result - ${inv.provider}`}>
      <div className="identity"><h3>{inv.result.executive_summary}</h3><span className={`pill ${inv.result.demo_mode ? 'warning' : 'healthy'}`}>{inv.result.demo_mode ? 'Demo fallback' : 'Gemini'}</span></div>
      <div className="columns"><List title="Observed Facts" items={inv.result.observed_symptoms} /><List title="Root-Cause Hypotheses" items={inv.result.plausible_root_causes} /><List title="Recommended Checks" items={inv.result.diagnostic_checks} /></div>
      <List title="Supporting Evidence" items={inv.result.evidence} />
      <h3>Sources</h3>{inv.result.source_references.length ? inv.result.source_references.map((s) => <details key={`${s.title}-${s.section}-${s.chunk_id}`}><summary>{s.title} - {s.section}</summary><p>{s.excerpt}</p></details>) : <Empty>No document references were retrieved.</Empty>}
      <p className="caution">{inv.result.uncertainty}</p>
    </Panel> : <Empty>No investigation has been created for this selected asset yet.</Empty>}
  </div>;
}

function WorkOrdersPage({ workOrders, audit, run, createOrder, busy }: { workOrders: WorkOrder[]; audit: AuditEvent[]; run: (label: string, fn: () => Promise<unknown>, message?: string) => Promise<void>; createOrder: () => Promise<void>; busy: string }) {
  const confirmRun = (message: string, label: string, fn: () => Promise<unknown>) => {
    if (window.confirm(message)) void run(label, fn);
  };
  return <div className="stack">
    <Panel title="Maintenance Work Orders" action={<button onClick={() => void createOrder()} disabled={!!busy}><Wrench size={17} />Create From Investigation</button>}>
      {workOrders.length ? <table><tbody>{workOrders.map((w) => <tr key={w.id}><td><strong>{w.id}</strong><br />{w.asset_id}</td><td><span className={`pill ${w.priority}`}>{w.priority}</span></td><td><span className={`pill ${w.status}`}>{w.status.replaceAll('_', ' ')}</span></td><td>{w.assigned_role}</td><td className="actions">{w.status === 'pending_approval' && <><button disabled={!!busy} onClick={() => confirmRun(`Approve ${w.id}? This records a human approval audit event.`, 'Approving', () => request(`/work-orders/${w.id}/approve`, { method: 'POST', body: JSON.stringify({ actor: 'Human approver' }) }))}>Approve</button><button disabled={!!busy} onClick={() => confirmRun(`Reject ${w.id}?`, 'Rejecting', () => request(`/work-orders/${w.id}/reject`, { method: 'POST', body: JSON.stringify({ actor: 'Human approver', notes: 'Not approved in demo' }) }))}>Reject</button></>}{w.status === 'approved' && <button disabled={!!busy} onClick={() => void run('Starting', () => request(`/work-orders/${w.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'in_progress', actor: 'Technician' }) }))}>Start</button>}{['approved', 'in_progress'].includes(w.status) && <button disabled={!!busy} onClick={() => confirmRun(`Complete ${w.id}?`, 'Completing', () => request(`/work-orders/${w.id}/complete`, { method: 'POST', body: JSON.stringify({ actor: 'Technician', notes: 'Inspection completed; follow-up readings stable in demo.' }) }))}>Complete</button>}</td></tr>)}</tbody></table> : <Empty>No work orders have been created yet.</Empty>}
    </Panel>
    <AuditPanel audit={audit.filter((event) => event.entity_type === 'work_order')} />
  </div>;
}

function KnowledgePage({ audit, run }: { audit: AuditEvent[]; run: (label: string, fn: () => Promise<unknown>, message?: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [query, setQuery] = useState('bearing vibration safety');
  const [hits, setHits] = useState<DocHit[]>([]);
  async function upload() {
    if (!file) throw new Error('Choose a text or PDF document first.');
    const body = new FormData();
    body.append('file', file);
    await request('/documents', { method: 'POST', body });
    setFile(null);
  }
  async function search() {
    setHits(await request<DocHit[]>(`/documents/search?q=${encodeURIComponent(query)}`));
  }
  return <div className="stack">
    <Panel title="Equipment Knowledge Retrieval" action={<button onClick={() => void run('Searching documents', search, 'Search complete.')}><Search size={17} />Search</button>}>
      <div className="formGrid">
        <label className="field"><span>Search query</span><input value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label className="field"><Upload size={16} /><input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
        <button onClick={() => void run('Uploading document', upload, 'Document uploaded and indexed.')}><Upload size={17} />Upload</button>
      </div>
      {hits.length ? hits.map((hit) => <details key={hit.chunk_id} open><summary>{hit.filename} - {hit.section} (score {hit.score})</summary><p>{hit.excerpt}</p></details>) : <Empty>Search the seeded maintenance guide or upload a supported document.</Empty>}
    </Panel>
    <AuditPanel audit={audit} />
  </div>;
}

function AuditPanel({ audit }: { audit: AuditEvent[] }) {
  return <Panel title="Audit Trail">{audit.length ? <table><tbody>{audit.slice(0, 12).map((event) => <tr key={event.id}><td>{formatTime(event.created_at)}</td><td>{event.entity_type}</td><td>{event.entity_id}</td><td>{event.action}</td><td>{event.actor}</td></tr>)}</tbody></table> : <Empty>No audit events recorded yet.</Empty>}</Panel>;
}

function EvaluationPage({ evaluation }: { evaluation: Record<string, unknown> | null }) {
  if (!evaluation) return <Empty>Evaluation metrics are loading.</Empty>;
  const definitions: Record<string, string> = {
    ground_truth_anomaly_readings: 'Seeded telemetry rows intentionally labeled abnormal.',
    detected_anomaly_windows: 'Persisted anomaly windows created by the detector.',
    false_alert_rate_note: 'Scope note for uncalibrated demo metrics.',
    detection_latency_hours: 'Synthetic scenario latency estimate.',
    current_risk_exposure: 'Sum of active anomaly risk scores.',
    estimated_cost_exposure_usd: 'Clearly labeled estimate, not measured savings.',
    work_orders: 'Persisted work-order counts.',
    calibration_warning: 'Risk-score limitation.',
  };
  return <div className="stats wide">{Object.entries(evaluation).map(([key, value]) => <div className="stat eval" key={key}><Activity size={18} /><div><span>{key.replaceAll('_', ' ')}</span><strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong><small>{definitions[key] || 'Metric definition documented in docs/evaluation.md.'}</small></div></div>)}</div>;
}

function DemoPage({ asset, anomaly, telemetry, investigation, orders, run, investigate, createOrder, busy }: { asset?: Asset; anomaly?: Anomaly; telemetry: Telemetry[]; investigation?: Investigation; orders: WorkOrder[]; run: (label: string, fn: () => Promise<unknown>, message?: string) => Promise<void>; investigate: () => Promise<Investigation | null>; createOrder: () => Promise<void>; busy: string }) {
  const [paused, setPaused] = useState(false);
  const order = orders.find((item) => item.status !== 'rejected' && item.status !== 'cancelled') || orders[0];
  const chartData = paused ? telemetry.slice(0, 48) : telemetry;
  const steps: [string, boolean][] = [
    ['Readings received', telemetry.length > 0],
    ['Anomaly detected', !!anomaly],
    ['Risk assessed', !!anomaly?.risk_score],
    ['AI investigation created', !!investigation],
    ['Work order created', !!order],
    ['Human approved', ['approved', 'in_progress', 'completed'].includes(order?.status || '')],
    ['Audit-ready completion', order?.status === 'completed'],
  ];
  return <div className="stack">
    <Panel title="Three-Minute Guided Scenario" action={<button disabled={!!busy} onClick={() => void run('Resetting scenario', () => request('/simulator/reset', { method: 'POST' }), 'Scenario reset to deterministic seed data.')}><RefreshCcw size={17} />Reset</button>}>
      <h3>{asset?.name}</h3><p>Sensor readings to anomaly detection to risk assessment to AI investigation to recommendation to work order to human approval to audit trail.</p>
      <div className="timeline">{steps.map(([label, done]) => <div className={done ? 'done' : ''} key={label}>{done ? <CheckCircle2 size={16} /> : <span />} {label}</div>)}</div>
      <div className="actions"><button disabled={!!busy} onClick={() => void run('Detecting', () => request('/anomalies/detect', { method: 'POST' }))}><Activity size={17} />Detect</button><button disabled={!!busy} onClick={() => void investigate()}><FileSearch size={17} />Investigate</button><button disabled={!!busy} onClick={() => void createOrder()}><Wrench size={17} />Create Work Order</button><button onClick={() => setPaused((value) => !value)}>{paused ? <Play size={17} /> : <Pause size={17} />}{paused ? 'Resume View' : 'Pause View'}</button>{order?.status === 'pending_approval' && <button disabled={!!busy} onClick={() => window.confirm(`Approve ${order.id}?`) && void run('Approving', () => request(`/work-orders/${order.id}/approve`, { method: 'POST', body: JSON.stringify({ actor: 'Judge approver' }) }))}>Approve</button>}{['approved', 'in_progress'].includes(order?.status || '') && <button disabled={!!busy} onClick={() => window.confirm(`Complete ${order.id}?`) && void run('Completing', () => request(`/work-orders/${order.id}/complete`, { method: 'POST', body: JSON.stringify({ actor: 'Technician', notes: 'Demo maintenance workflow completed with approval.' }) }))}>Complete</button>}</div>
    </Panel>
    <Panel title="Live Scenario Readings"><ResponsiveContainer height={280}><LineChart data={chartData}><CartesianGrid stroke="#263241" /><XAxis dataKey="timestamp" hide /><YAxis /><Tooltip /><Line dataKey="vibration" name="Vibration (mm/s)" stroke="#86efac" dot={false} /><Line dataKey="temperature" name="Temp (deg C)" stroke="#22d3ee" dot={false} /></LineChart></ResponsiveContainer></Panel>
  </div>;
}

function List({ title, items }: { title: string; items: string[] }) {
  return <div><h3>{title}</h3>{items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <Empty>Not available.</Empty>}</div>;
}

createRoot(document.getElementById('root')!).render(<App />);
