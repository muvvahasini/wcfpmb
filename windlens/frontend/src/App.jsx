import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get } from "./api.js";

const TZ = "Europe/London";
const mw = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-GB"));
const signed = (n) => (n == null ? "–" : `${n > 0 ? "+" : ""}${Math.round(n).toLocaleString("en-GB")}`);
const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const stamp = (iso) => new Date(iso).toLocaleString("en-GB", { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const longDay = (iso) => new Date(iso).toLocaleDateString("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });

function useApi(path, params, enabled = true) {
  const [s, set] = useState({ data: null, error: null, loading: enabled });
  const key = JSON.stringify(params);
  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    set((p) => ({ ...p, loading: true, error: null }));
    get(path, params, ctrl.signal)
      .then((data) => set({ data, error: null, loading: false }))
      .catch((e) => e.name !== "AbortError" && set({ data: null, error: e.message, loading: false }));
    return () => ctrl.abort();
  }, [path, key, enabled]);
  return s;
}

function Panel({ title, note, state, children }) {
  return (
    <section className="panel">
      <header><h2>{title}</h2>{note && <p>{note}</p>}</header>
      {state?.error ? <p className="error" role="alert">{state.error}</p>
        : state?.loading && !state?.data ? <div className="skeleton" aria-busy="true" />
        : children}
    </section>
  );
}

const Kpi = ({ label, value, unit, hint }) => (
  <div className="kpi" title={hint}>
    <span className="kpi-label">{label}</span>
    <span className="kpi-value">{value}<small>{unit}</small></span>
  </div>
);

export default function App() {
  const [date, setDate] = useState("");
  const [cutoff, setCutoff] = useState("09:20");
  const [picked, setPicked] = useState(null);

  const meta = useApi("metadata", { cutoff });
  useEffect(() => {
    const m = meta.data;
    if (m && (!date || date < m.min_date || date > m.max_date)) setDate(m.min_date);
  }, [meta.data]);

  const day = useApi("day", { date, cutoff }, !!date);
  const acc = useApi("accuracy", { start: meta.data?.min_date, end: meta.data?.max_date, cutoff }, !!meta.data);
  const hist = useApi("forecast-history", { delivery_time: picked, cutoff }, !!picked);
  useEffect(() => setPicked(null), [date, cutoff]);

  const d = day.data, m = d?.metrics;
  const rows = d?.rows.map((r) => ({ ...r, label: clock(r.startTime) }));
  const decided = d && stamp(d.cutoff_utc);

  return (
    <div className="app">
      <header className="top">
        <div><h1>WindLens</h1><span>January 2026 · national GB wind · day-ahead decisions</span></div>
        <span className="status">{meta.data ? `Data: ${meta.data.min_date} to ${meta.data.max_date} delivery days` : meta.error ?? "Loading data…"}</span>
      </header>

      <div className="controls">
        <label>Delivery day
          <input type="date" value={date} min={meta.data?.min_date} max={meta.data?.max_date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <label>Decision cutoff (UK time, day before)
          <input type="time" value={cutoff} onChange={(e) => e.target.value && setCutoff(e.target.value)} />
        </label>
        <p className="cutoff-line">{d ? <>Decision made <b>{decided}</b>. Only forecasts published by then count.</> : "Choose a delivery day."}</p>
      </div>

      <aside className="scope-note">
        <strong>Wind forecast decision support—not a total procurement calculation.</strong>
        <span>This view shows the wind forecast available for a January 2026 day-ahead purchase decision and its quantified historical error. It does not calculate total power requirements or how much additional power to buy; demand and other generation are outside the specified data scope.</span>
      </aside>

      {day.error && <p className="error" role="alert">{day.error}</p>}

      <div className="kpis">
        <Kpi label="Decision-time wind forecast, daily mean" value={mw(d?.mean_forecast)} unit=" MW" hint="Average of the latest forecasts available by the selected cutoff" />
        <Kpi label="Actual wind, matched-hour mean" value={mw(d?.mean_actual)} unit=" MW" hint="Mean actual generation for hours with a complete pair of half-hour readings and a forecast" />
        <Kpi label="Historical MAE" value={mw(m?.mae)} unit=" MW" hint="Mean absolute error for matched intervals" />
        <Kpi label="Historical RMSE" value={mw(m?.rmse)} unit=" MW" hint="Root mean squared error; larger misses have more influence" />
        <Kpi label="Historical bias" value={signed(m?.bias)} unit=" MW" hint="Positive = forecast too high (over-forecast), negative = too low" />
        <Kpi label="Matched intervals" value={m ? `${m.matched}/${m.forecast_intervals}` : "–"} hint="Delivery intervals with both a forecast and an actual" />
      </div>

      <Panel title="Wind forecast available at decision time vs actual" note="The forecast is the latest version available by the selected cutoff. Click a point to inspect its forecast history." state={day}>
        <div className="chart tall">
          <ResponsiveContainer>
            <LineChart data={rows} onClick={(e) => e?.activePayload && setPicked(e.activePayload[0].payload.startTime)}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="label" interval={5} stroke="var(--muted)" />
              <YAxis stroke="var(--muted)" tickFormatter={mw} width={56} label={{ value: "MW", angle: -90, position: "insideLeft", fill: "var(--muted)" }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }} formatter={(v) => `${mw(v)} MW`} />
              <Line name="Wind forecast at decision time" dataKey="forecast" stroke="var(--wind)" dot={false} strokeWidth={2} />
              <Line name="Actual wind generation" dataKey="actual" stroke="var(--actual)" dot={false} strokeWidth={2} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="legend"><i className="sw wind" /> Wind forecast at cutoff <i className="sw actual" /> Actual wind generation</p>
      </Panel>

      {picked && (
        <Panel title={`Forecast versions for ${longDay(picked)} ${clock(picked)}`} note={hist.data && `Cutoff ${stamp(hist.data.cutoff_utc)}`} state={hist}>
          <table>
            <thead><tr><th>Published</th><th className="num">Forecast (MW)</th><th>Status</th></tr></thead>
            <tbody>
              {hist.data?.versions.map((v) => (
                <tr key={v.publishTime} className={v.selected ? "sel" : v.available_at_cutoff ? "" : "late"}>
                  <td>{stamp(v.publishTime)}</td><td className="num">{mw(v.forecast)}</td>
                  <td>{v.selected ? "Used for the decision" : v.available_at_cutoff ? "Available, superseded" : "Published too late"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <Panel title="Accuracy over the full period" note={acc.data && `${acc.data.overall.matched}/${acc.data.overall.forecast_intervals} forecast hours matched to complete actual hours · MAPE ${acc.data.overall.mape?.toFixed(1) ?? "–"}% (near-zero actuals excluded)`} state={acc}>
        {acc.data && (
          <>
            <div className="kpis small">
              <Kpi label="MAE" value={mw(acc.data.overall.mae)} unit=" MW" />
              <Kpi label="RMSE" value={mw(acc.data.overall.rmse)} unit=" MW" />
              <Kpi label="Bias" value={signed(acc.data.overall.bias)} unit=" MW" />
              <Kpi label="90th percentile miss" value={mw(acc.data.overall.p90_abs_error)} unit=" MW" hint="9 in 10 matched hours were within this error" />
            </div>
            <div className="grid2">
              <div><h3>MAE by delivery day (MW)</h3>
                <div className="chart"><ResponsiveContainer><BarChart data={acc.data.daily}>
                  <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="delivery_date" tickFormatter={(s) => s.slice(8)} stroke="var(--muted)" /><YAxis stroke="var(--muted)" tickFormatter={mw} width={50} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }} formatter={(v) => `${mw(v)} MW`} /><Bar dataKey="mae" fill="var(--wind)" />
                  {date && <ReferenceLine x={date} stroke="var(--actual)" />}
                </BarChart></ResponsiveContainer></div></div>
              <div><h3>MAE by delivery hour (UK)</h3>
                <div className="chart"><ResponsiveContainer><BarChart data={acc.data.by_hour}>
                  <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="hour" stroke="var(--muted)" /><YAxis stroke="var(--muted)" tickFormatter={mw} width={50} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }} formatter={(v, n, p) => [`${mw(v)} MW (avg lead ${p.payload.horizon_h.toFixed(0)} h)`, "MAE"]} /><Bar dataKey="mae" fill="var(--actual)" />
                </BarChart></ResponsiveContainer></div></div>
            </div>
          </>
        )}
      </Panel>

      <Panel title="Hourly forecast and actual detail" note="Each actual is the mean of the two source half-hour readings for that hour; incomplete hours are not scored." state={day}>
        <div className="scroll"><table>
          <thead><tr><th>Delivery hour (UK)</th><th className="num">Forecast (MW)</th><th>Published</th><th className="num">Actual mean (MW)</th><th className="num">Error (MW)</th><th className="num">Abs error (MW)</th></tr></thead>
          <tbody>{rows?.map((r) => (
            <tr key={r.startTime} onClick={() => setPicked(r.startTime)}>
              <td>{r.label}</td><td className="num">{mw(r.forecast)}</td><td>{stamp(r.publishTime)}</td>
              <td className="num">{mw(r.actual)}</td><td className="num">{signed(r.error)}</td><td className="num">{mw(r.abs_error)}</td>
            </tr>))}</tbody>
        </table></div>
      </Panel>

      <details className="panel method">
        <summary>Method and limits</summary>
        <ul>
          <li>Source: Elexon BMRS FUELHH (actual wind generation) and WINDFOR (wind forecasts), at GB national level. No other generation, demand, or external datasets are used.</li>
          <li>Before analysis, the processing script keeps valid WIND actuals, drops rows with missing or invalid required values, removes exact duplicates, and excludes every record in a conflicting duplicate delivery-time group. Original downloads are preserved; cleaned data and a processing report are stored in <code>data/processed/</code>.</li>
          <li>Potential outliers are flagged separately for actuals and for each forecast publication. A value is removed from analysis when it differs from the median of up to three neighboring records on either side by more than the larger of 2,000 MW or six scaled median absolute deviations (MAD × 1.4826). Flagged rows are retained in separate CSVs for review.</li>
          <li>This rolling-MAD rule is a heuristic, not proof that a reading is wrong. A genuine, sharp change in wind generation may be excluded, and the rule may miss bad values that are not isolated spikes. Review the processing report and flagged rows when interpreting results.</li>
          <li>For each delivery interval, the dashboard selects the latest forecast published by the cutoff on the previous UK calendar day. Later forecasts are shown in the history but are not used for the decision-time comparison.</li>
          <li>WINDFOR forecasts are hourly while FUELHH actuals are half-hourly. The two actual readings within each UTC delivery hour are averaged to align with the forecast; hours missing either reading are excluded rather than scored using partial data. The delivery view and accuracy metrics use these hourly values.</li>
          <li>Error = forecast − hourly mean actual. Positive bias means over-forecasting. Metrics include only hours with both a selected forecast and a complete actual; missing values are not filled with zero. MAPE excludes actual generation at or below 100 MW.</li>
          <li>The app is limited to purchase decisions made in January 2026, corresponding to delivery dates 2 January through 1 February 2026. The cutoff defaults to 09:20 UK time and is adjustable; check it against your own trading deadline.</li>
          <li>Demand data is out of scope, so this tool evaluates wind forecasts and their errors; it cannot calculate total power requirements or recommend how much to buy or sell.</li>
        </ul>
      </details>
    </div>
  );
}
