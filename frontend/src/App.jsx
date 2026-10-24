import { useCallback, useEffect, useState } from 'react';
import { Activity, ArrowDownUp, ArrowRight, ArrowUpRight, Boxes, Check, CircleAlert, Code2, Database, ExternalLink, FileCode2, FlaskConical, Layers3, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react';

function normalizeUrl(url) {
  if (!url) return '';
  const trimmed = String(url).trim().replace(/\/+$/, '');
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

const services = {
  fastapi: { label: 'FastAPI', short: 'FastAPI', color: 'fastapi', url: normalizeUrl(import.meta.env.VITE_FASTAPI_URL || 'http://localhost:8000'), docs: '/docs', tagline: 'Type hints · automatic OpenAPI · synchronous handlers' },
  drf: { label: 'Django REST Framework', short: 'Django REST', color: 'drf', url: normalizeUrl(import.meta.env.VITE_DRF_URL || 'http://localhost:8001'), docs: '/api/schema/swagger-ui/', tagline: 'Serializers · Django ecosystem · synchronous views' },
};
const blank = { title: '', description: '', price: '', category: '', stock: 0, image: '' };
const endpoint = '/api/v1';

async function request(key, path, options = {}) {
  const started = performance.now();
  try {
    const response = await fetch(`${services[key].url}${endpoint}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    return { status: response.status, data, latency: +(performance.now() - started).toFixed(2) };
  } catch (error) {
    return { status: 'OFFLINE', data: { detail: error.message || 'Could not reach the API' }, latency: +(performance.now() - started).toFixed(2) };
  }
}

function errorText(data) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((e) => `${Array.isArray(e.loc) ? e.loc.filter((p) => p !== 'body').join('.') : ''}: ${e.msg || 'Invalid value'}`).join(' · ');
  if (detail && typeof detail === 'object') return Object.entries(detail).map(([field, issues]) => `${field}: ${Array.isArray(issues) ? issues.join(', ') : issues}`).join(' · ');
  return data?.message || 'Request failed';
}

export default function App() {
  const [backend, setBackend] = useState('fastapi');
  const [products, setProducts] = useState([]);
  const [meta, setMeta] = useState({ total: 0 });
  const [health, setHealth] = useState('checking');
  const [listResult, setListResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [benchmark, setBenchmark] = useState(null);
  const [quality, setQuality] = useState(null);
  const [locReport, setLocReport] = useState(null);
  const [labResults, setLabResults] = useState([]);
  const [labBusy, setLabBusy] = useState(false);
  const service = services[backend];

  const load = useCallback(async () => {
    setLoading(true);
    const [list, status] = await Promise.all([
      request(backend, `/products?q=${encodeURIComponent(query)}&limit=100`), request(backend, '/health'),
    ]);
    setListResult(list);
    if (list.status >= 200 && list.status < 300) { setProducts(list.data.data || []); setMeta(list.data.meta || { total: 0 }); }
    else { setProducts([]); setMeta({ total: 0 }); }
    setHealth(status.status >= 200 && status.status < 300 ? (status.data.data?.status || status.data.status || 'ok') : 'offline');
    setLoading(false);
  }, [backend, query]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    Promise.all([
      fetch('/benchmark-results/latest.json').then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('/quality-results/loc.json').then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('/quality-results/latest.json').then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([b, l, q]) => { setBenchmark(b); setLocReport(l); setQuality(q); });
  }, []);

  const notify = (message, kind = 'success') => { setToast({ message, kind }); window.setTimeout(() => setToast(null), 5000); };
  const beginEdit = (p) => { setEditing(p.id); setForm({ ...p, price: String(p.price) }); setShowForm(true); };
  const submit = async (event) => {
    event.preventDefault(); setBusy(true);
    const payload = { title: form.title, description: form.description, price: Number(form.price), category: form.category, stock: Number(form.stock), image: form.image };
    const result = await request(backend, editing ? `/products/${editing}` : '/products', { method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    if (result.status === (editing ? 200 : 201)) { setForm(blank); setEditing(null); setShowForm(false); notify(editing ? 'Product updated' : 'Product added'); await load(); }
    else notify(errorText(result.data), 'error');
    setBusy(false);
  };
  const remove = async (id) => {
    if (!window.confirm('Delete this product?')) return;
    const result = await request(backend, `/products/${id}`, { method: 'DELETE' });
    if (result.status >= 200 && result.status < 300) { notify('Product removed'); load(); } else notify(errorText(result.data), 'error');
  };
  const importData = async () => {
    setBusy(true);
    const result = await request(backend, '/products/import-dummyjson', { method: 'POST' });
    if (result.status >= 200 && result.status < 300) {
      const d = result.data.data || {};
      notify(`Fetched ${d.fetched ?? 0} · created ${d.created ?? 0} · skipped ${d.skipped ?? d.existing ?? 0}${d.cache_hit ? ' · cached upstream response' : ''}`);
      await load();
    } else notify(errorText(result.data), 'error');
    setBusy(false);
  };

  const runContractLab = async () => {
    setLabBusy(true); setLabResults([]);
    const cases = [
      ['Valid payload', 'POST', '/products', { title: 'Contract lab item', description: 'Temporary validation scenario', price: 12.5, category: 'Testing', stock: 3, image: 'https://dummyjson.com/image/400x300' }, 201, true],
      ['Missing title', 'POST', '/products', { price: 12.5, category: 'Testing' }, 422],
      ['Price is zero', 'POST', '/products', { title: 'Lab item', price: 0, category: 'Testing' }, 422],
      ['Price below minimum', 'POST', '/products', { title: 'Lab item', price: 0.001, category: 'Testing' }, 422],
      ['Negative stock', 'POST', '/products', { title: 'Lab item', price: 12.5, category: 'Testing', stock: -1 }, 422],
      ['Invalid image URL', 'POST', '/products', { title: 'Lab item', price: 12.5, category: 'Testing', image: 'not a url' }, 422],
      ['Unexpected field', 'POST', '/products', { title: 'Lab item', price: 12.5, category: 'Testing', surprise: true }, 422],
      ['Wrong types', 'POST', '/products', { title: ['bad'], price: 'nope', category: 'Testing' }, 422],
    ];
    const results = [];
    for (const key of ['fastapi', 'drf']) {
      const list = await request(key, '/products?limit=1');
      let firstProduct = list.data?.data?.[0];
      let firstId = firstProduct?.id;
      let temporaryId = null;
      if (firstId === undefined) {
        const seed = await request(key, '/products', { method: 'POST', body: JSON.stringify({ title: 'Temporary lab fixture', price: 1, category: 'Testing', stock: 0 }) });
        if (seed.status === 201) { firstId = seed.data?.data?.id; firstProduct = seed.data.data; temporaryId = firstId; }
      }
      for (const [name, method, path, body, expected, cleanup] of cases) {
        const result = await request(key, path, { method, body: JSON.stringify(body) });
        results.push({ name, key, expected, ...result, passed: result.status === expected });
        if (cleanup && result.status === 201) await request(key, `/products/${result.data?.data?.id}`, { method: 'DELETE' });
      }
      if (firstId !== undefined) {
        const empty = await request(key, `/products/${firstId}`, { method: 'PATCH', body: '{}' });
        results.push({ name: 'Empty PATCH', key, expected: 422, ...empty, passed: empty.status === 422 });
        const original = firstProduct;
        const patch = await request(key, `/products/${firstId}`, { method: 'PATCH', body: JSON.stringify({ stock: Number(original.stock) + 1 }) });
        results.push({ name: 'Valid PATCH', key, expected: 200, ...patch, passed: patch.status === 200 });
        if (patch.status === 200) await request(key, `/products/${firstId}`, { method: 'PATCH', body: JSON.stringify({ stock: original.stock }) });
      }
      if (temporaryId !== null) await request(key, `/products/${temporaryId}`, { method: 'DELETE' });
      const missing = await request(key, '/products/2147483000');
      results.push({ name: 'Missing product', key, expected: 404, ...missing, passed: missing.status === 404 });
    }
    setLabResults(results); setLabBusy(false);
  };
  const quickValidation = async () => {
    const result = await request(backend, '/validation/example', { method: 'POST', body: JSON.stringify({ title: 'x', price: -1, category: '' }) });
    notify(result.status >= 400 ? `${service.short} rejected the invalid payload (${result.status}): ${errorText(result.data)}` : 'The sample payload passed unexpectedly.', result.status >= 400 ? 'success' : 'error');
  };

  return <div className="app-shell" id="top" data-framework={backend}>
    <div className="ambient ambient-one"/><div className="ambient ambient-two"/>
    <header className="site-header"><a className="brand" href="#top"><span className="brand-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg></span><span className="brand-name"><b>API</b><span>ARCHITECTS</span></span></a><span className="system-online"><i/>System Online</span></header>

    <main className="page-content">
      <section className="hero-section"><h1>The Backend <em className={backend}>Showdown</em></h1><p>Evaluating Python’s top web frameworks by building the same product catalog API. Compare syntax, performance, and validation strategies.</p>
        <div className="framework-toggle" aria-label="Select API backend"><button className={backend === 'fastapi' ? 'active fastapi-active' : ''} onClick={() => setBackend('fastapi')}><svg className="fastapi-mark" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22ZM12 4C16.4183 4 20 7.58172 20 12C20 16.4183 16.4183 20 12 20C7.58172 20 4 16.4183 4 12ZM10.5 7.5V11H7.5V13H10.5V16.5L16.5 12L10.5 7.5Z"/></svg><span>FastAPI</span></button><button className={backend === 'drf' ? 'active drf-active' : ''} onClick={() => setBackend('drf')}><svg className="drf-mark" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M11 2L2 7L11 12L20 7L11 2ZM11 15L2 10L11 5L20 10L11 15ZM11 22L2 17L11 12L20 17L11 22Z"/></svg><span>Django REST</span></button></div>
      </section>

      <section id="live-api" className="glass-card live-api-card"><div className="card-title-row"><div><div className="eyebrow"><span/> LIVE API ENDPOINT</div><h2><code>GET /api/v1/products</code></h2><p className="card-subtitle">Local catalog from the selected backend’s independent SQLite database.</p></div><div className="endpoint-actions"><span className={`status-chip ${health === 'offline' ? 'is-offline' : ''}`}><i/>{health === 'offline' ? 'API OFFLINE' : health === 'checking' ? 'CHECKING' : 'API ONLINE'}</span><a href={`${service.url}${service.docs}`} target="_blank" rel="noreferrer" className="icon-link" title="Open interactive API docs"><ExternalLink size={17}/></a></div></div>
        <div className="catalog-controls"><label className="search-box"><Search size={16}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products or categories"/></label><div className="catalog-actions"><button className="button quiet" disabled={busy} onClick={importData}><ArrowDownUp size={15}/> Import DummyJSON</button><button className="button primary" onClick={() => { setEditing(null); setForm(blank); setShowForm(true); }}><Plus size={16}/> Add product</button><button className="button square" onClick={load} disabled={loading} title="Refresh"><RefreshCw size={15}/></button></div></div>
        <div className="table-wrap"><table><thead><tr><th>PRODUCT</th><th>CATEGORY</th><th>PRICE</th><th>INVENTORY</th><th>STATUS</th><th/></tr></thead><tbody>{products.map((p) => <tr key={p.id}><td><div className="product-cell"><div className="product-thumb">{p.image ? <img src={p.image} onError={(e) => { e.currentTarget.style.display = 'none'; }} alt=""/> : <Boxes size={18}/>}</div><div><b>{p.title}</b><small>{p.description || 'No description'}</small></div></div></td><td><span className="category-tag">{p.category}</span></td><td className="price-cell">${Number(p.price).toFixed(2)}</td><td>{p.stock}</td><td><span className={`stock-badge ${p.stock > 10 ? 'in-stock' : p.stock > 0 ? 'low-stock' : 'out-stock'}`}><i/>{p.stock > 10 ? 'In stock' : p.stock > 0 ? 'Low stock' : 'Out of stock'}</span></td><td><div className="row-actions"><button title="Edit product" onClick={() => beginEdit(p)}><FileCode2 size={15}/></button><button title="Delete product" onClick={() => remove(p.id)}><Trash2 size={15}/></button></div></td></tr>)}</tbody></table>
          {!products.length && <div className="empty-state">{loading ? <RefreshCw size={22} className="spin"/> : health === 'offline' ? <CircleAlert size={24}/> : <Boxes size={24}/>}<b>{loading ? 'Loading the product catalog…' : health === 'offline' ? 'Backend is not responding' : 'No products found'}</b><span>{health === 'offline' ? `Check that ${service.short} is running, then retry.` : 'Add a product or adjust the search.'}</span>{health === 'offline' && <button className="button quiet" onClick={load}>Retry connection</button>}</div>}
        </div>
        <div className="api-footer"><span>{loading ? 'Request in progress…' : `${products.length} shown · ${meta.total ?? 0} total`}</span><span>HTTP {listResult?.status ?? '—'} · {listResult ? `${listResult.latency} ms` : '—'} · {service.short}</span><span><Database size={13}/> Persisted locally</span></div>
      </section>

      <section className="showcase-grid"><article className="glass-card code-card"><div className="eyebrow">IMPLEMENTATION CODE</div><h2>Same feature. Different tools.</h2><p className="card-subtitle">Short examples of the real synchronous patterns used in this project.</p><div className="code-tabs"><div><span className="code-lang fastapi-text">FASTAPI</span><pre><code><span className="code-muted"># Pydantic input model</span>{'\n'}<span className="code-purple">class</span> ProductInput(BaseModel):{'\n'}  title: str{'\n'}  price: <span className="code-yellow">float</span> = Field(ge=<span className="code-green">0.01</span>){'\n'}  stock: <span className="code-yellow">int</span> = Field(ge=<span className="code-green">0</span>){'\n\n'}<span className="code-purple">def</span> <span className="code-blue">list_products</span>():{'\n'}  <span className="code-purple">return</span> {`{"data": ...}`}</code></pre></div><div><span className="code-lang drf-text">DJANGO REST</span><pre><code><span className="code-muted"># Serializer validation</span>{'\n'}<span className="code-purple">class</span> ProductSerializer(serializers.ModelSerializer):{'\n'}  price = serializers.DecimalField({'\n'}    max_digits=<span className="code-green">10</span>, decimal_places=<span className="code-green">2</span>,{'\n'}    min_value=<span className="code-green">Decimal</span>(<span className="code-yellow">"0.01"</span>)){'\n\n'}<span className="code-purple">def</span> <span className="code-blue">get</span>(self, request):{'\n'}  <span className="code-purple">return</span> Response({`{"data": ...}`})</code></pre></div></div><div className="code-note"><Activity size={15}/> Both current request handlers use regular synchronous functions.</div></article>
        <div className="showcase-stack"><BenchmarkCard benchmark={benchmark} backend={backend}/><ValidationCard quality={quality} onTry={quickValidation}/></div></section>

      <section id="comparison" className="glass-card comparison-section"><div className="section-head"><div><div className="eyebrow">MEASURED EVIDENCE</div><h2>Framework comparison</h2><p className="card-subtitle">Values load from the generated project reports. No performance values are embedded in the UI.</p></div><span className={`report-chip ${benchmark?.status === 'measured' ? 'report-live' : ''}`}>{benchmark?.status === 'measured' ? 'MEASURED' : 'PENDING'}</span></div>
        <div className="comparison-table-wrap"><table className="comparison-table"><thead><tr><th>MEASURE</th><th><span className="fastapi-text">●</span> FastAPI</th><th><span className="drf-text">●</span> Django REST</th></tr></thead><tbody>
          {['health', 'product_list', 'product_retrieve'].map((key) => <tr key={key}><td>{key === 'product_retrieve' ? 'Single product retrieval' : key === 'product_list' ? 'Product list' : 'Health check'}<small>Mean / median / P95 latency</small></td><MetricCells report={benchmark} metric={key}/></tr>)}
          <tr><td>Throughput<small>Requests per second, each route</small></td><td>{metricRange(benchmark, 'fastapi', 'product_list', 'requests_per_second')}<small>list requests/s</small></td><td>{metricRange(benchmark, 'drf', 'product_list', 'requests_per_second')}<small>list requests/s</small></td></tr>
          <tr><td>Equivalent feature code<small>LOC per counting rules</small></td><td>{locReport?.framework_feature_loc?.FastAPI?.total ?? '—'} LOC</td><td>{locReport?.framework_feature_loc?.DRF?.total ?? '—'} LOC</td></tr>
        </tbody></table></div>
        <div className="report-meta"><span>Timestamp: {benchmark?.measured_at_utc || 'No fresh benchmark report'}</span><span>Samples: {benchmark?.configuration?.request_count && benchmark?.configuration?.trials ? `${benchmark.configuration.request_count * benchmark.configuration.trials} per route` : '—'}</span><span>Warm-up: {benchmark?.configuration?.warmup_count ?? '—'} requests</span><span>Concurrency: {benchmark?.configuration?.concurrency ?? '—'}</span></div>
        <div className="comparison-lower"><div><b>Test run</b><span>{quality ? `${quality.status} · ${quality.passed} passed · ${quality.failed} failed` : 'No test report yet'}</span><small>{quality?.measured_at_utc || ''}</small></div><div><b>Count boundaries</b><span>{locReport ? `${locReport.total_application_loc} application LOC · ${locReport.framework_configuration_and_scripts_loc} config/scripts · ${locReport.generated_migration_loc} generated migrations · ${locReport.test_loc_excluded_from_application_total} test LOC excluded` : 'LOC report not available'}</span></div></div>
      </section>

      <section id="testing-lab" className="glass-card lab-section"><div className="section-head"><div><div className="eyebrow">SAME REQUESTS · BOTH BACKENDS</div><h2>API testing lab</h2><p className="card-subtitle">Run equivalent create, update, and validation requests against each live service.</p></div><button className="button primary" disabled={labBusy} onClick={runContractLab}><FlaskConical size={15}/>{labBusy ? 'Running scenarios…' : 'Run all scenarios'}</button></div>
        <div className="scenario-chips">{['Valid payload', 'Missing title', 'Price is zero', 'Price below minimum', 'Negative stock', 'Invalid image URL', 'Unexpected field', 'Wrong types', 'Empty PATCH', 'Valid PATCH', 'Missing product'].map((name) => <span key={name}>{name}</span>)}</div>
        {!labResults.length && <div className="lab-placeholder"><FlaskConical size={20}/><span>Results show expected and actual status, request time, and both JSON responses.</span></div>}
        {labResults.length > 0 && <div className="lab-results">{Array.from(new Set(labResults.map((r) => r.name))).map((name) => { const rows = labResults.filter((r) => r.name === name); const expected = rows[0]?.expected; const passed = rows.length === 2 && rows.every((r) => r.passed); return <article className="lab-case" key={name}><div className="case-heading"><b>{name}</b><span>Expected HTTP {expected}</span><strong className={passed ? 'pass' : 'fail'}>{passed ? 'PASS' : 'CHECK'}</strong></div><div className="case-backends">{['fastapi', 'drf'].map((key) => { const r = rows.find((row) => row.key === key); return <div className="case-backend" key={key}><div><b className={`${key}-text`}>{services[key].short}</b><span>HTTP {r?.status ?? '—'} · {r?.latency ?? '—'} ms</span><strong className={r?.passed ? 'pass' : 'fail'}>{r?.passed ? 'PASS' : 'FAIL'}</strong></div><details><summary>Response JSON</summary><pre>{JSON.stringify(r?.data ?? {}, null, 2)}</pre></details></div>; })}</div></article>; })}</div>}
      </section>

      <section id="research" className="research-grid"><article className="glass-card research-card"><div className="eyebrow">RESEARCH FINDINGS</div><h2>What the comparison shows</h2><div className="research-row"><span className="research-icon fastapi-bg"><Sparkles size={17}/></span><div><b>FastAPI</b><p>Uses Pydantic schemas and generates OpenAPI documentation from route declarations. In this prototype the route handlers and SQLite access are synchronous.</p></div></div><div className="research-row"><span className="research-icon drf-bg"><ShieldCheck size={17}/></span><div><b>Django REST Framework</b><p>Uses serializers for input validation and Django’s request/response ecosystem. Its built-in conventions can suit applications already using Django.</p></div></div><div className="research-row"><span className="research-icon neutral-bg"><Database size={17}/></span><div><b>Separate local catalogs</b><p>Each backend persists its own SQLite data. Import copies public DummyJSON products into that local catalog; switching backends changes the database being viewed.</p></div></div><p className="research-footnote">Benchmark results depend on this machine, server settings, dataset, and trial conditions. They do not establish a universal winner.</p></article>
        <article className="glass-card docs-card"><div className="eyebrow">API DOCUMENTATION</div><h2>Explore the live endpoints</h2><p className="card-subtitle">Open each backend’s interactive schema and try the same requests.</p>{['fastapi', 'drf'].map((key) => <a className="docs-row" key={key} href={`${services[key].url}${services[key].docs}`} target="_blank" rel="noreferrer"><span className={`docs-mark ${key}-bg`}>{key === 'fastapi' ? <Code2 size={17}/> : <Layers3 size={17}/>}</span><span><b>{services[key].short}</b><small>{services[key].url}{services[key].docs}</small></span><ArrowUpRight size={16}/></a>)}<a className="research-link" href="https://fastapi.tiangolo.com/async/" target="_blank" rel="noreferrer">FastAPI sync and async guide <ArrowRight size={14}/></a><p className="docs-note">Upstream data source: <a href="https://dummyjson.com/" target="_blank" rel="noreferrer">DummyJSON</a>. Imports use backend-side caching and do not proxy the source on every catalog request.</p></article></section>
      <footer className="site-footer"><span>Compare with evidence. Choose for your context.</span></footer>
    </main>

    {showForm && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}><form className="product-modal glass-card" onSubmit={submit}><div className="modal-head"><div><div className="eyebrow">PRODUCT CATALOG</div><h2>{editing ? 'Edit product' : 'Add a product'}</h2></div><button type="button" className="icon-button" onClick={() => setShowForm(false)}><X size={19}/></button></div><label>Product name<input required minLength="2" maxLength="120" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Everyday tote bag"/></label><label>Description<textarea maxLength="500" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="A short product description"/></label><div className="form-pair"><label>Price (USD)<input required type="number" min="0.01" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="24.00"/></label><label>Stock<input required type="number" min="0" step="1" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })}/></label></div><div className="form-pair"><label>Category<input required maxLength="80" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Accessories"/></label><label>Image URL<input type="url" value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} placeholder="https://…"/></label></div><div className="modal-actions"><button type="button" className="button quiet" onClick={() => setShowForm(false)}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : <><Plus size={15}/> Create product</>}</button></div></form></div>}
    {toast && <div className={`toast ${toast.kind}`} role="status">{toast.kind === 'error' ? <CircleAlert size={16}/> : <Check size={16}/>}<span>{toast.message}</span><button aria-label="Dismiss notification" onClick={() => setToast(null)}><X size={14}/></button></div>}
  </div>;
}

function BenchmarkCard({ benchmark, backend }) {
  const reports = benchmark?.[backend]; const list = reports?.product_list; const retrieve = reports?.product_retrieve;
  return <article className="glass-card benchmark-card"><div className="eyebrow">PERFORMANCE BENCHMARK</div><div className="card-heading-inline"><h2>{benchmark?.status === 'measured' ? 'Measured request times' : 'Awaiting fresh run'}</h2><Activity size={17}/></div>{benchmark?.status === 'measured' ? <><div className="bench-stat"><span>Product list · mean latency</span><b>{list?.mean_latency_ms ?? '—'} <small>ms</small></b><div className="bench-track"><i style={{ width: `${barWidth(list?.mean_latency_ms, retrieve?.mean_latency_ms)}%` }}/></div></div><div className="bench-duo"><div><span>Median</span><b>{list?.median_latency_ms ?? '—'} ms</b></div><div><span>P95</span><b>{list?.p95_latency_ms ?? '—'} ms</b></div><div><span>Throughput</span><b>{list?.requests_per_second ?? '—'} /s</b></div><div><span>Single retrieval</span><b>{retrieve?.mean_latency_ms ?? '—'} ms mean</b></div></div><small className="bench-foot">n={list?.sample_count ?? '—'} · {benchmark.measured_at_utc || ''}</small></> : <p className="card-subtitle">Run <code>python scripts/benchmark.py</code> to generate real local API measurements. Health-only historical figures are labeled in the report.</p>}</article>;
}
function ValidationCard({ quality, onTry }) { return <article className="glass-card validation-card"><div className="eyebrow">DATA VALIDATION</div><div className="card-heading-inline"><h2>Errors you can inspect</h2><ShieldCheck size={17}/></div><p>Both APIs reject invalid product data. Error envelopes follow each framework’s native format while the status codes and rules match.</p><div className="validation-meta"><span>Latest suite</span><b>{quality ? `${quality.passed} passed · ${quality.failed} failed` : 'No report loaded'}</b></div><button className="text-action" onClick={onTry}>Send an invalid payload <ArrowUpRight size={14}/></button></article>; }
function MetricCells({ report, metric }) { return ['fastapi', 'drf'].map((key) => { const m = report?.[key]?.[metric]; return <td key={key}>{m ? `${m.mean_latency_ms} / ${m.median_latency_ms} / ${m.p95_latency_ms} ms` : '—'}<small>{m ? `n=${m.sample_count} · ${m.requests_per_second} req/s` : 'measurement pending'}</small></td>; }); }
function metricRange(report, framework, route, key) { const v = report?.[framework]?.[route]?.[key]; return v == null ? '—' : `${v} req/s`; }
function barWidth(a, b) { if (!Number.isFinite(Number(a)) || !Number.isFinite(Number(b))) return 0; return Math.max(8, Math.min(100, Number(a) / Math.max(Number(a), Number(b)) * 100)); }
