/* DriveScope dashboard renderer — data-driven from the engine result.
   Renders: event selector, KPI cards, animated car, multi-lane scope (scrub),
   scorecard (issues), calibration actions. Robust to missing channels. */
(function (global) {
  const NS = "http://www.w3.org/2000/svg";
  const E = (t, a) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const elH = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

  // ---- closed-loop longitudinal plant: smooth target + 2nd-order driveline (shuffle) ----
  // The driveline is excited by the torque RATE (d/dt target); calibration knobs shape that
  // excitation (rate, fill smear, lash) and the damping (anti-shuffle), so the simulated ax
  // shows snatch/shuffle/clunk that the user can tune out. LTI in `gain` (used for baseline fit).
  function plantSim(target, dt, k) {
    const n = target.length, out = new Float64Array(n);
    const drive = new Float64Array(n);
    for (let i = 1; i < n; i++) drive[i] = (target[i] - target[i - 1]) / dt;   // torque rate
    // clutch-fill smear (moving average of the excitation over the fill window)
    const fw = Math.max(1, Math.round(k.fill / dt));
    const ds = new Float64Array(n); let acc = 0;
    for (let i = 0; i < n; i++) { acc += drive[i]; if (i >= fw) acc -= drive[i - fw]; ds[i] = acc / Math.min(i + 1, fw); }
    const wn = k.wn, zeta = k.zeta, gain = k.gain, sharp = k.sharp;
    let x = 0, xd = 0;
    for (let i = 0; i < n; i++) {
      let lash = 0;                                   // clunk on torque reversal, reduced by lash comp
      if (i > 1) { const s0 = Math.sign(target[i] - target[i - 1]), s1 = Math.sign(target[i - 1] - target[i - 2]); if (s0 && s1 && s0 !== s1) lash = (1 - k.lash) * (target[i] - 2 * target[i - 1] + target[i - 2]) / (dt * dt) * 0.015; }
      const u = gain * sharp * ds[i] + lash;
      const xdd = wn * wn * u - 2 * zeta * wn * xd - wn * wn * x;
      xd += xdd * dt; x += xd * dt;
      if (!isFinite(x)) { x = 0; xd = 0; }
      out[i] = target[i] + x;
    }
    return out;
  }
  function peakRing(sim, target) { let p = 0; for (let i = 0; i < sim.length; i++) p = Math.max(p, Math.abs(sim[i] - target[i])); return p; }
  function ringRMS(sim, target) { let a = 0; for (let i = 0; i < sim.length; i++) { const d = sim[i] - target[i]; a += d * d; } return Math.sqrt(a / sim.length); }

  // canonical signal -> display style
  const SIG = {
    ax_filt:       { label: "ax (filtered)", col: "#ff5347", unit: "m/s²", w: 2.4 },
    ax_raw:        { label: "ax (raw)",      col: "#ff534766", unit: "m/s²", w: 1.0 },
    pedal:         { label: "Pedal",         col: "#9b2c2c", unit: "%", w: 1.6 },
    gear_act:      { label: "Gear actual",   col: "#e6edf3", unit: "", w: 2.0 },
    gear_tgt:      { label: "Gear target",   col: "#f0883e", unit: "", w: 1.6, dash: "5 4" },
    engine_speed:  { label: "EngSpeed",      col: "#3b8bff", unit: "rpm", w: 1.9 },
    turbine_speed: { label: "TurbSpeed",     col: "#5fc8ff", unit: "rpm", w: 1.4 },
    eng_trq:       { label: "Crank torque",  col: "#e0a82e", unit: "Nm", w: 1.9 },
    vehicle_speed: { label: "Vehicle speed", col: "#3fce6a", unit: "kph", w: 1.9 },
  };
  const SEVCOL = { bad: "#ff5347", warn: "#e3b341", ok: "#3fce6a", na: "#7d8a99" };

  function autorange(arr, incZero) {
    let lo = Math.min(...arr), hi = Math.max(...arr);
    if (incZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (hi - lo < 1e-6) hi = lo + 1;
    const pad = (hi - lo) * 0.08; return [lo - pad, hi + pad];
  }

  // build the lane list for an event from whatever signals are present
  function buildLanes(s) {
    const L = [];
    if (s.ax_filt) L.push({ keys: ["ax_filt", "ax_raw"], primary: "ax_filt", h: 150, big: true, incZero: true, fixed: [-3, 9] });
    if (s.pedal || s.gear_act) L.push({ keys: ["pedal"], gears: ["gear_tgt", "gear_act"], primary: "pedal", h: 98, fixed: [0, 100], gearScale: true });
    if (s.engine_speed) L.push({ keys: ["engine_speed", "turbine_speed"], primary: "engine_speed", h: 92, incZero: true });
    if (s.eng_trq) L.push({ keys: ["eng_trq"], primary: "eng_trq", h: 76, incZero: true });
    if (s.vehicle_speed) L.push({ keys: ["vehicle_speed"], primary: "vehicle_speed", h: 76, incZero: true });
    return L;
  }

  function renderApp(root, result) {
    root.innerHTML = "";
    const head = elH("div", "ds-head");
    head.appendChild(elH("div", null,
      `<div class="ds-title">DriveScope — Drivability Diagnostic <span class="ds-tag">measured</span></div>
       <div class="ds-fname">${result.file.split("/").pop()} · ${result.duration[0]}–${result.duration[1]} s · ${result.n_events} event(s)</div>`));
    root.appendChild(head);

    // channel resolution summary
    const nun = (result.channels_unresolved || []).length;
    const chip = elH("div", "ds-chan",
      `<b>Channels:</b> ${Object.keys(result.channels_resolved).length} resolved` +
      (nun ? ` · <span style="color:#e3b341">${nun} unresolved: ${result.channels_unresolved.join(", ")}</span>` : ` · <span style="color:#3fce6a">all mapped</span>`));
    root.appendChild(chip);

    if (!result.events.length) {
      const wrap = elH("div", "ds-empty");
      let html = "No drivability events were auto-detected in this recording.";
      const d = result.debug;
      if (d) {
        const sg = d.signals || {};
        const fmt = (k, u) => sg[k] ? `${sg[k].min}–${sg[k].max}${u || ""}` : "—";
        html += `<div class="ds-diag"><b>Recording diagnostic</b><br>` +
          `vehicle speed: <b>${fmt("vehicle_speed", " kph")}</b> · ` +
          `pedal: <b>${fmt("pedal", " %")}</b> · ` +
          `engine: <b>${fmt("engine_speed", " rpm")}</b> · ` +
          `ax: <b>${fmt("ax_filt", " m/s²")}</b><br>` +
          `standstill segments: <b>${d.standstill_segments ?? "—"}</b> · ` +
          `tip-ins (pedal→${50}%): <b>${d.tipins ?? "—"}</b> · ` +
          `gear changes: <b>${d.gear_changes ?? "—"}</b>` +
          (d.gears_seen ? ` · gears seen: <b>${d.gears_seen.join(",")}</b>` : "") +
          `<br><span class="ds-diaghint">If the speed never drops near 0, the vehicle-speed channel may be mismatched; ` +
          `if pedal max is 0, the pedal channel is wrong. Use a custom channel map, or send this file to tune detection.</span></div>`;
      }
      wrap.innerHTML = html;
      root.appendChild(wrap);
      return;
    }

    // event-type overview
    const TYPE_LABEL = {
      drive_away: "Drive-away", drive_away_ess: "Drive-away ESS",
      accel_constant_load: "Accel constant load", accel_load_increase: "Accel load increase",
      kickdown_downshift: "Kick-down downshift", poweron_upshift: "Power-on upshift",
      tip_out_overrun: "Tip-out / overrun", lever_change: "Garage shift", decel_coast:"Decel (coast)",decel_brake:"Decel (brake)",tip_in_cstspd:"Tip-in cst speed",tip_out_cstspd:"Tip-out cst speed",engine_start:"Engine start",engine_stop:"Engine stop",idle:"Idle",
    };
    if (result.by_type) {
      const ov = elH("div", "ds-chan");
      ov.innerHTML = "<b>Detected:</b> " + Object.entries(result.by_type)
        .map(([k, n]) => `${n}× ${TYPE_LABEL[k] || k}`).join(" &nbsp;·&nbsp; ");
      root.appendChild(ov);
    }

    // event selector
    const tabs = elH("div", "ds-tabs");
    result.events.forEach((ev, i) => {
      const b = elH("button", "ds-tab" + (i === 0 ? " active" : ""),
        `<span class="ds-dot" style="background:${SEVCOL[ev.verdict] || "#7d8a99"}"></span>${ev.sdv || ev.label}<span class="ds-tw">${ev.window.t0}s</span>`);
      b.onclick = () => { tabs.querySelectorAll(".ds-tab").forEach(x => x.classList.remove("active")); b.classList.add("active"); drawEvent(ev); };
      tabs.appendChild(b);
    });
    root.appendChild(tabs);

    const body = elH("div", "ds-body"); root.appendChild(body);
    drawEvent(result.events[0]);

    function drawEvent(ev) {
      body.innerHTML = "";
      const m = ev.metrics, s = ev.signals;

      // ---- SDV identity header ----
      if (ev.sdv) {
        const verdC = { bad: "#ff5347", warn: "#e3b341", ok: "#3fce6a" }[ev.verdict] || "#7d8a99";
        body.appendChild(elH("div", "ds-sdvhdr",
          `<span class="ds-sdvname">${ev.sdv}</span>` +
          (ev.group ? `<span class="ds-sdvgrp">${ev.group}</span>` : "") +
          `<span class="ds-sdvverd" style="color:${verdC};border-color:${verdC}">${(ev.verdict || "").toUpperCase()}</span>` +
          `<span class="ds-sdvwin">${ev.window.t0}–${ev.window.t1}s</span>`));
      }

      // ---- KPI cards (engine-provided, maneuver-specific) ----
      const cards = elH("div", "ds-cards");
      const kpis = ev.kpis && ev.kpis.length ? ev.kpis : [];
      cards.innerHTML = kpis.map(c =>
        `<div class="ds-card ${c.sev}"><div class="ds-k">${c.k}</div><div class="ds-v">${c.v}</div><div class="ds-s">${c.sub || ""}</div></div>`
      ).join("");
      body.appendChild(cards);

      // ---- scope + car panel ----
      const panel = elH("div", "ds-panel");
      panel.innerHTML = `<div class="ds-scene"><div class="ds-hilbar">
          <span class="ds-led"></span><span class="ds-runtxt">RUN</span>
          <span class="ds-hm">SIM&nbsp;<b class="ds-simt">0.00</b>s</span>
          <span class="ds-hm">CYCLE&nbsp;<b class="ds-cyc">0.0</b>s</span>
          <span class="ds-hm">RATE&nbsp;<b class="ds-rate">—</b></span>
          <span class="ds-hm">PLANT&nbsp;<b class="ds-plant">GEMT6</b></span>
          <span class="ds-hm">STATE&nbsp;<b class="ds-state">—</b></span>
          <span class="ds-hm ds-track">◷ Chelsea P.G.</span>
          <button class="ds-xray-btn ds-xray-on" type="button">X-RAY</button></div>
        <div class="ds-phase">—</div><svg class="ds-car"></svg></div>
        <svg class="ds-cluster"></svg>
        <svg class="ds-ptrain"></svg>
        <div class="ds-scopewrap"><svg class="ds-scope"></svg><div class="ds-readout"></div></div>
        <div class="ds-issuebar"></div>
        <div class="ds-ctrls">
          <button class="ds-play active">Pause</button><button class="ds-restart">Restart</button>
          <button class="ds-spd active" data-s="0.5">0.5×</button><button class="ds-spd" data-s="1">1×</button><button class="ds-spd" data-s="0.25">0.25×</button>
          <span class="ds-hint">drag the scope to scrub · click an issue to seek · HIL replay</span></div>`;
      body.appendChild(panel);

      // ---- scorecard + actions ----
      const grid = elH("div", "ds-grid2");
      const sc = elH("div", "ds-sect");
      sc.appendChild(elH("h3", null, `ODRIV criteria${ev.sdv ? " — " + ev.sdv : ""}`));
      const crit = ev.criteria || [];
      if (crit.length) {
        const issueByCrit = {};
        (ev.issues || []).forEach(i => { issueByCrit[i.title.toLowerCase()] = i.detail; });
        let rows = "";
        crit.forEach(c => {
          const meas = c.measured || "<span style='color:#5a6675'>not measured</span>";
          const pill = c.sev === "na"
            ? `<span class="ds-pill na">—</span>`
            : `<span class="ds-pill ${c.sev}">${c.sev === "meas" ? "MEAS" : c.sev.toUpperCase()}</span>`;
          const dr = c.driv ? `<span class="ds-driv">P${c.driv}</span>` : "";
          rows += `<tr><td>${c.criteria}${dr}</td><td class="num">${c.t ?? "—"}</td><td class="num">${c.wl ?? "—"}</td><td class="num">${meas}</td><td>${pill}</td></tr>`;
        });
        const tbl = elH("table", null,
          `<thead><tr><th>Criterion</th><th class="num">Target</th><th class="num">Warn</th><th class="num">Measured</th><th>Status</th></tr></thead><tbody>${rows}</tbody>`);
        sc.appendChild(tbl);
        sc.appendChild(elH("div", "ds-note",
          "Target / Warn are ODRIV rating limits (0–10). Measured values are DriveScope physical estimates from the raw signal — shown for orientation, not as AVL ratings."));
      } else {
        sc.appendChild(elH("div", "ds-empty", "No ODRIV criteria mapped for this SDV."));
      }
      grid.appendChild(sc);

      const ac = elH("div", "ds-sect");
      ac.appendChild(elH("h3", null, "Calibration actions"));
      if (ev.actions.length) {
        ev.actions.forEach(a => {
          ac.appendChild(elH("div", "ds-act",
            `<div class="ds-n">${a.priority}</div><div class="ds-ab"><b>${a.title}</b> <span class="ds-prio p${a.priority}">P${a.priority}</span><br><span>${a.detail}</span></div>`));
        });
      } else ac.appendChild(elH("div", "ds-empty", "No actions required — within targets."));
      // key findings (issue details) under actions
      if (ev.issues && ev.issues.length) {
        ac.appendChild(elH("h3", null, "Key findings"));
        ev.issues.forEach(i => {
          ac.appendChild(elH("div", "ds-find",
            `<span class="ds-pill ${i.severity}">${i.severity.toUpperCase()}</span> <b>${i.title}</b> — ${i.value}<div class="ds-idet">${i.detail}</div>`));
        });
      }
      grid.appendChild(ac);
      body.appendChild(grid);

      wireScope(panel, ev);
    }

    function sevOf(v, warn, bad) { if (v == null) return "na"; const a = Math.abs(v); return a >= bad ? "bad" : a >= warn ? "warn" : "ok"; }

    // ---------- scope + car wiring ----------
    function wireScope(panel, ev) {
      const m = ev.metrics, s = ev.signals, t = s.t, N = t.length;
      const T0 = t[0], T1 = t[N - 1];
      const lanes = buildLanes(s);
      const scope = panel.querySelector(".ds-scope");
      const carSvg = panel.querySelector(".ds-car");
      const phaseEl = panel.querySelector(".ds-phase");
      const ro = panel.querySelector(".ds-readout");

      const SW = 1000, ML = 56, MR = 50, MT = 8, MB = 22, PW = SW - ML - MR;
      let acc = MT; lanes.forEach(L => { L.top = acc; acc += L.h + 12; });
      const SH = acc - 12 + MB;
      scope.setAttribute("viewBox", `0 0 ${SW} ${SH}`);
      const xOf = tt => ML + PW * (tt - T0) / (T1 - T0);
      const tOf = x => T0 + (x - ML) / PW * (T1 - T0);

      // per-lane range
      lanes.forEach(L => {
        let lo, hi;
        if (L.fixed) [lo, hi] = L.fixed;
        else { [lo, hi] = autorange(s[L.primary], L.incZero); }
        L.lo = lo; L.hi = hi;
        L.yOf = v => L.top + L.h * (1 - (v - lo) / (hi - lo));
      });

      // phase bands
      const ti = m.ti, teng = m.teng, hasShift = !!m.has_shift;
      const band = (a, b, c, op) => scope.appendChild(E("rect", { x: xOf(a), y: MT, width: xOf(b) - xOf(a), height: SH - MT - MB, fill: c, opacity: op }));
      if (hasShift) {
        band(T0, ti, "#3fce6a", .04);
        band(ti, teng, "#a371f7", .12);
        band(teng, teng + 0.22, "#f0883e", .15);
        band(teng + 0.22, teng + 1.05, "#e3b341", .09);
      } else {
        // non-shift maneuver: highlight the analysis window only
        band(ti, T1, "#3b8bff", .05);
      }

      // lane frames, ticks, labels
      lanes.forEach(L => {
        scope.appendChild(E("rect", { x: ML, y: L.top, width: PW, height: L.h, fill: "none", stroke: "#1c2430", "stroke-width": 1 }));
        const nt = L.big ? 5 : 4;
        for (let i = 0; i <= nt; i++) {
          const v = L.lo + (L.hi - L.lo) * i / nt, y = L.yOf(v);
          scope.appendChild(E("line", { x1: ML, y1: y, x2: ML + PW, y2: y, stroke: "#1a212b", "stroke-width": 1, opacity: i && i < nt ? .5 : .9 }));
          const tx = E("text", { x: ML - 5, y: y + 3, fill: "#7d8a99", "font-size": 9, "text-anchor": "end", "font-family": "monospace" }); tx.textContent = Math.round(v); scope.appendChild(tx);
        }
        const lab = E("text", { x: ML + 6, y: L.top + 12, fill: SIG[L.primary].col, "font-size": 10.5, "font-weight": 600 });
        lab.textContent = L.keys.map(k => s[k] ? SIG[k].label : null).filter(Boolean).join(" / ") + (L.gears ? " + Gear" : "");
        scope.appendChild(lab);
        const un = E("text", { x: ML + PW - 5, y: L.top + 12, fill: "#7d8a99", "font-size": 9, "text-anchor": "end" }); un.textContent = SIG[L.primary].unit; scope.appendChild(un);
      });

      // time axis
      for (let tt = Math.ceil(T0); tt <= T1; tt++) {
        const x = xOf(tt);
        scope.appendChild(E("line", { x1: x, y1: MT, x2: x, y2: SH - MB, stroke: "#1a212b", "stroke-width": 1, opacity: .3 }));
        const tx = E("text", { x, y: SH - 7, fill: "#7d8a99", "font-size": 9, "text-anchor": "middle", "font-family": "monospace" }); tx.textContent = tt + "s"; scope.appendChild(tx);
      }
      // markers
      const mk = (tt, c, lbl, ytop) => { if (tt == null) return; const x = xOf(tt); scope.appendChild(E("line", { x1: x, y1: MT, x2: x, y2: SH - MB, stroke: c, "stroke-width": 1.1, "stroke-dasharray": "5 4", opacity: .8 })); const tx = E("text", { x: x + 3, y: ytop, fill: c, "font-size": 9, "font-weight": 600 }); tx.textContent = lbl; scope.appendChild(tx); };
      mk(ti, "#a371f7", hasShift ? "trigger" : "event start", MT + 22);
      if (hasShift) {
        if (m.tdec != null) mk(m.tdec, "#79c0ff", "decide (+" + m.dec_ms + "ms)", MT + 34);
        mk(teng, "#f0883e", "engage" + (m.tot_ms != null ? " (+" + m.tot_ms + "ms→ax)" : ""), MT + 22);
      }

      // trace path
      const tracePath = (arr, L, col, w, dash) => {
        let d = ""; for (let i = 0; i < N; i++) { const x = xOf(t[i]), y = L.yOf(Math.max(L.lo, Math.min(L.hi, arr[i]))); d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); }
        const p = E("path", { d, fill: "none", stroke: col, "stroke-width": w, "stroke-linejoin": "round" }); if (dash) p.setAttribute("stroke-dasharray", dash); scope.appendChild(p);
      };
      lanes.forEach(L => {
        // pedal filled
        if (L.primary === "pedal" && s.pedal) {
          let d = "M" + xOf(t[0]) + " " + L.yOf(0);
          for (let i = 0; i < N; i++) d += "L" + xOf(t[i]).toFixed(1) + " " + L.yOf(Math.max(0, Math.min(100, s.pedal[i]))).toFixed(1);
          d += "L" + xOf(t[N - 1]) + " " + L.yOf(0) + "Z";
          scope.appendChild(E("path", { d, fill: "#9b2c2c", opacity: .15 }));
        }
        L.keys.forEach(k => { if (s[k]) tracePath(s[k], L, SIG[k].col, SIG[k].w, SIG[k].dash); });
        // gear overlays scaled into pedal lane (gear*25)
        if (L.gears) {
          const gm = g => g * 25;
          ["gear_tgt", "gear_act"].forEach(gk => { if (s[gk]) tracePath(s[gk].map(gm), L, SIG[gk].col, SIG[gk].w, SIG[gk].dash); });
          for (let g = 1; g <= 4; g++) { const y = L.yOf(g * 25); scope.appendChild(E("text", { x: ML + PW + 4, y: y + 3, fill: "#7d8a99", "font-size": 8.5, "font-family": "monospace" })).textContent = "G" + g; }
        }
      });

      // execution span annotation on ax lane (shift events only)
      const axLane = lanes[0];
      if (hasShift && isFinite(ti) && isFinite(teng) && teng > ti) {
        const y = axLane.top + axLane.h - 10, x1 = xOf(ti), x2 = xOf(teng);
        scope.appendChild(E("line", { x1, y1: y, x2, y2: y, stroke: "#a371f7", "stroke-width": 1.3 }));
        [x1, x2].forEach(xx => scope.appendChild(E("line", { x1: xx, y1: y - 4, x2: xx, y2: y + 4, stroke: "#a371f7", "stroke-width": 1.3 })));
        const tx = E("text", { x: (x1 + x2) / 2, y: y - 5, fill: "#d2b8ff", "font-size": 9.5, "font-weight": 700, "text-anchor": "middle" });
        tx.textContent = "◄ " + (m.exec_ms ?? "?") + " ms execution ►"; scope.appendChild(tx);
      }

      const cursor = E("line", { x1: xOf(teng), y1: MT, x2: xOf(teng), y2: SH - MB, stroke: "#fff", "stroke-width": 1, opacity: .85 }); scope.appendChild(cursor);
      const axDot = E("circle", { r: 4, fill: "#fff", stroke: "#ff5347", "stroke-width": 2 }); scope.appendChild(axDot);

      // ---- exact-time issue markers ----
      const MKCOL = { bad: "#ff5347", warn: "#e3b341", info: "#5a86c4" };
      const markers = (ev.markers || []).filter(mm => mm.t >= T0 && mm.t <= T1);
      let seekTo = null; // set after loop; markers can call it
      markers.forEach(mm => {
        const col = MKCOL[mm.severity] || MKCOL.info;
        const x = xOf(mm.t);
        const isIssue = mm.severity === "bad" || mm.severity === "warn";
        if (mm.t_end && mm.t_end > mm.t) {
          scope.appendChild(E("rect", { x, y: MT, width: Math.max(2, xOf(mm.t_end) - x), height: SH - MT - MB, fill: col, opacity: isIssue ? .12 : .07 }));
        }
        scope.appendChild(E("line", { x1: x, y1: MT, x2: x, y2: SH - MB, stroke: col, "stroke-width": isIssue ? 1.6 : 1, "stroke-dasharray": isIssue ? "" : "3 3", opacity: isIssue ? .95 : .6 }));
        // flag handle at top (clickable)
        const flag = E("g", { class: "ds-mk", style: "cursor:pointer" });
        flag.appendChild(E("rect", { x: x - 1.5, y: MT, width: 3, height: 9, fill: col }));
        const tw = 7 + mm.label.length * 5.4;
        const fx = Math.min(x + 2, SW - MR - tw);
        flag.appendChild(E("rect", { x: fx, y: MT - 1, width: tw, height: 13, rx: 2, fill: "#0c1118", stroke: col, "stroke-width": .8, opacity: .96 }));
        const ftx = E("text", { x: fx + 4, y: MT + 8.5, fill: col, "font-size": 8.5, "font-weight": 600, "font-family": "monospace" }); ftx.textContent = mm.label; flag.appendChild(ftx);
        flag.addEventListener("pointerdown", e => { e.stopPropagation(); if (seekTo) seekTo(mm.t); });
        scope.appendChild(flag);
      });

      // ================= closed-loop HIL plant (what-if calibration) =================
      const val = (arr, tt) => { let lo = 0, hi = N - 1; while (lo < hi) { const md = (lo + hi) >> 1; if (t[md] < tt) lo = md + 1; else hi = md; } if (lo <= 0) return arr[0]; const f = (tt - t[lo - 1]) / (t[lo] - t[lo - 1]); return arr[lo - 1] + (arr[lo] - arr[lo - 1]) * f; };
      const ax = tt => s.ax_filt ? val(s.ax_filt, tt) : 0;
      const az = tt => s.az_raw ? val(s.az_raw, tt) : 0;
      const axBase = tt => { let a = 0, w = 0; for (let d = -0.22; d <= 0.22; d += 0.044) { const k = Math.exp(-d * d / 0.016); a += ax(tt + d) * k; w += k; } return a / w; };
      // fine uniform grids over the window
      const SDT = 0.005, SN = Math.max(8, Math.min(6000, Math.round((T1 - T0) / SDT)));
      const simTime = new Float64Array(SN), meas = new Float64Array(SN), target = new Float64Array(SN);
      for (let i = 0; i < SN; i++) { const tt = T0 + i * SDT; simTime[i] = tt; meas[i] = ax(tt); }
      { const half = Math.max(1, Math.round(0.12 / SDT)); for (let i = 0; i < SN; i++) { let a = 0, c = 0; for (let kk = -half; kk <= half; kk++) { const j = i + kk; if (j >= 0 && j < SN) { a += meas[j]; c++; } } target[i] = a / c; } }
      const measPeak = peakRing(meas, target) || 0.5;
      const fHz = (m.fs && m.fs >= 0.8 && m.fs <= 4) ? m.fs : 1.8;
      const WN = 2 * Math.PI * fHz;
      // baseline knobs (UI units) and fit gain so baseline sim ~ measured artifact level
      const base = { rate: 1.0, fill: 0.02, damp: 0.0, lash: 0.3 };
      const kFrom = (ui, gain) => ({ wn: WN, zeta: 0.06 + ui.damp * 0.30, gain, sharp: ui.rate, fill: ui.fill, lash: ui.lash });
      let fitGain = 1.0;
      { const probe = plantSim(target, SDT, kFrom(base, 1.0)); const pk = peakRing(probe, target) || 1e-3; fitGain = measPeak / pk; }
      const baseSim = plantSim(target, SDT, kFrom(base, fitGain));
      const baseSnatch = (() => { let p = 0; for (let i = 1; i < SN; i++) p = Math.max(p, (baseSim[i] - baseSim[i - 1]) / SDT); return p; })();
      const baseShuffle = ringRMS(baseSim, target);
      let knobs = { ...base }, curSim = baseSim, simMode = false;
      const axSimAt = tt => { const f = (tt - T0) / SDT; const i = Math.max(0, Math.min(SN - 2, Math.floor(f))); return curSim[i] + (curSim[i + 1] - curSim[i]) * (f - i); };
      const axTgtAt = tt => { const f = (tt - T0) / SDT; const i = Math.max(0, Math.min(SN - 2, Math.floor(f))); return target[i] + (target[i + 1] - target[i]) * (f - i); };
      // simulated trace on the ax lane (dashed cyan)
      const clampY = v => Math.max(axLane.lo, Math.min(axLane.hi, v));
      const simPath = E("path", { d: "", fill: "none", stroke: "#22d3ee", "stroke-width": 1.8, "stroke-dasharray": "6 4", opacity: 0 }); scope.appendChild(simPath);
      function redrawSim() {
        let d = "";
        for (let i = 0; i < SN; i += 2) { d += (i ? "L" : "M") + xOf(simTime[i]).toFixed(1) + " " + axLane.yOf(clampY(curSim[i])).toFixed(1); }
        simPath.setAttribute("d", d); simPath.setAttribute("opacity", simMode ? 0.95 : 0);
      }
      carSvg.setAttribute("viewBox", "0 0 1000 210");
      carSvg.innerHTML = `
        <defs>
          <linearGradient id="ds-body" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#7d8a9b"/><stop offset="0.18" stop-color="#5b6675"/>
            <stop offset="0.55" stop-color="#3d4654"/><stop offset="1" stop-color="#252c37"/>
          </linearGradient>
          <linearGradient id="ds-glass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#2b3a4d"/><stop offset="1" stop-color="#0f1620"/>
          </linearGradient>
          <radialGradient id="ds-rim" cx="0.42" cy="0.4" r="0.7">
            <stop offset="0" stop-color="#d4dce6"/><stop offset="0.55" stop-color="#9aa6b4"/><stop offset="1" stop-color="#5b6573"/>
          </radialGradient>
          <radialGradient id="ds-tire" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0.62" stop-color="#161b22"/><stop offset="0.85" stop-color="#0c1015"/><stop offset="1" stop-color="#070a0e"/>
          </radialGradient>
          <radialGradient id="ds-shadow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stop-color="#000" stop-opacity="0.45"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
          </radialGradient>
          <linearGradient id="ds-eng" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#ff7d63"/><stop offset="0.5" stop-color="#d23a23"/><stop offset="1" stop-color="#7e1c11"/>
          </linearGradient>
          <linearGradient id="ds-mech" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#9aa6b6"/><stop offset="1" stop-color="#475061"/>
          </linearGradient>
          <filter id="ds-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <linearGradient id="ds-sheen" x1="0" y1="0" x2="0.8" y2="1">
            <stop offset="0.36" stop-color="#fff" stop-opacity="0"/><stop offset="0.49" stop-color="#fff" stop-opacity="0.20"/>
            <stop offset="0.54" stop-color="#fff" stop-opacity="0.05"/><stop offset="0.7" stop-color="#fff" stop-opacity="0"/>
          </linearGradient>
          <clipPath id="ds-bodyclip"><path d="M244 150 L262 150 A38 38 0 0 0 338 150 L662 150 A38 38 0 0 0 738 150 L792 150
                     Q807 150 807 134 L806 119 Q805 108 790 104 L720 98 Q705 82 672 70 L648 60
                     Q632 53 596 51 L398 51 Q358 52 338 68 L312 90 Q288 99 264 107 Q246 113 244 130 Z"/></clipPath>
        </defs>
        <rect x="0" y="180" width="1000" height="30" fill="#0a0e13"/>
        <line x1="0" y1="180" x2="1000" y2="180" stroke="#222c38" stroke-width="1.5"/>
        <g class="ds-refl" opacity="0.10">
          <path d="M244 150 L262 150 A38 38 0 0 0 338 150 L662 150 A38 38 0 0 0 738 150 L792 150
                   Q807 150 807 134 L806 119 Q805 108 790 104 L720 98 Q705 82 672 70 L648 60
                   Q632 53 596 51 L398 51 Q358 52 338 68 L312 90 Q288 99 264 107 Q246 113 244 130 Z"
                fill="url(#ds-body)" transform="translate(0,361) scale(1,-1)"/>
        </g>
        <g class="ds-grd"></g>
        <ellipse class="ds-shadow" cx="500" cy="183" rx="285" ry="11" fill="url(#ds-shadow)"/>
        <g class="ds-veh">
          <g class="ds-wfar" opacity="0.6">
            <circle cx="320" cy="140" r="31" fill="#0a0d12" stroke="#05080b" stroke-width="1.2"/>
            <circle cx="320" cy="140" r="16" fill="url(#ds-rim)" opacity="0.7"/>
            <circle cx="680" cy="140" r="31" fill="#0a0d12" stroke="#05080b" stroke-width="1.2"/>
            <circle cx="680" cy="140" r="16" fill="url(#ds-rim)" opacity="0.7"/>
          </g>
          <g class="ds-wR"></g><g class="ds-wF"></g>
          <g class="ds-pt">
            <line class="ds-tflow" x1="700" y1="140" x2="300" y2="150" stroke="#ff7043" stroke-width="3" stroke-linecap="round" opacity="0.0" filter="url(#ds-glow)"/>
            <rect x="330" y="147" width="300" height="5" rx="2.5" fill="url(#ds-mech)" stroke="#10161f" stroke-width="0.6"/>
            <circle cx="312" cy="150" r="14" fill="url(#ds-mech)" stroke="#10161f" stroke-width="1"/>
            <circle cx="312" cy="150" r="6" fill="#2a323d"/>
            <line x1="312" y1="150" x2="300" y2="166" stroke="url(#ds-mech)" stroke-width="5" stroke-linecap="round"/>
            <rect x="560" y="128" width="92" height="30" rx="6" fill="url(#ds-mech)" stroke="#10161f" stroke-width="1"/>
            <ellipse cx="652" cy="143" rx="11" ry="15" fill="url(#ds-mech)" stroke="#10161f" stroke-width="1"/>
            <rect x="648" y="118" width="96" height="42" rx="7" fill="url(#ds-eng)" stroke="#3a0f08" stroke-width="1.2"/>
            <rect x="660" y="106" width="72" height="16" rx="4" fill="url(#ds-eng)" stroke="#3a0f08" stroke-width="1"/>
            <line x1="672" y1="120" x2="672" y2="158" stroke="#5a160c" stroke-width="2"/>
            <line x1="690" y1="120" x2="690" y2="158" stroke="#5a160c" stroke-width="2"/>
            <line x1="708" y1="120" x2="708" y2="158" stroke="#5a160c" stroke-width="2"/>
            <line x1="726" y1="120" x2="726" y2="158" stroke="#5a160c" stroke-width="2"/>
            <circle cx="742" cy="128" r="8" fill="url(#ds-mech)" stroke="#10161f" stroke-width="1"/>
            <circle cx="742" cy="128" r="3.5" fill="#2a323d"/>
          </g>
          <g class="ds-cb">
            <path class="ds-body-fill" d="M244 150 L262 150 A38 38 0 0 0 338 150 L662 150 A38 38 0 0 0 738 150 L792 150
                     Q807 150 807 134 L806 119 Q805 108 790 104 L720 98 Q705 82 672 70 L648 60
                     Q632 53 596 51 L398 51 Q358 52 338 68 L312 90 Q288 99 264 107 Q246 113 244 130 Z"
                  fill="url(#ds-body)" stroke="#aeb9c8" stroke-width="1.4" fill-opacity="0.32"/>
            <path d="M330 66 Q430 55 600 55 Q655 56 690 73 L674 79 Q636 60 600 60 L404 60 Q372 61 351 73 Z" fill="#eef4fb" opacity="0.16"/>
            <ellipse cx="745" cy="112" rx="52" ry="8" fill="#cdd9e6" opacity="0.12"/>
            <path d="M262 152 L738 152" stroke="#04070a" stroke-width="2.5" opacity="0.55" stroke-linecap="round"/>
            <g clip-path="url(#ds-bodyclip)">
              <rect x="244" y="48" width="563" height="104" fill="url(#ds-sheen)"/>
              <ellipse cx="430" cy="64" rx="170" ry="16" fill="#ffffff" opacity="0.05"/>
            </g>
            <path d="M690 99 Q703 84 672 72 L650 63 Q636 56 600 55 L402 55 Q364 56 346 70 L324 89 Z"
                  fill="url(#ds-glass)" stroke="#10161f" stroke-width="1" fill-opacity="0.45"/>
            <line x1="512" y1="55" x2="512" y2="93" stroke="#46566a" stroke-width="2.4"/>
            <path d="M470 150 L470 60" stroke="#46566a" stroke-width="1.2" opacity="0.5"/>
            <rect x="792" y="118" width="16" height="11" rx="3" fill="#bfe2ff" opacity="0.9"/>
            <rect x="246" y="116" width="9" height="13" rx="2.5" fill="#ff5d52"/>
          </g>
        </g>
        <g class="ds-gv">
          <text class="ds-gvlbl" x="470" y="70" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="#4ea3ff" font-weight="700"></text>
          <line class="ds-gvln" x1="470" y1="92" x2="470" y2="92" stroke="#4ea3ff" stroke-width="3.5" stroke-linecap="round"/>
          <polygon class="ds-gvhd" points="" fill="#4ea3ff"/>
        </g>`;
      const dashes = carSvg.querySelector(".ds-grd");
      for (let i = 0; i < 18; i++) dashes.appendChild(E("rect", { x: i * 70, y: 191, width: 36, height: 3, rx: 1.5, fill: "#1c2632" }));
      const cb = carSvg.querySelector(".ds-cb");
      const veh = carSvg.querySelector(".ds-veh");
      const shadow = carSvg.querySelector(".ds-shadow");
      const gvln = carSvg.querySelector(".ds-gvln"), gvhd = carSvg.querySelector(".ds-gvhd"), gvtx = carSvg.querySelector(".ds-gvlbl");
      function wheel(host, cx) {
        host.innerHTML = "";
        host.appendChild(E("circle", { cx, cy: 148, r: 33, fill: "url(#ds-tire)", stroke: "#05080b", "stroke-width": 1.5 }));
        host.appendChild(E("circle", { cx, cy: 148, r: 24, fill: "#0b0f15" }));
        host.appendChild(E("circle", { cx, cy: 148, r: 22, fill: "none", stroke: "#2a3340", "stroke-width": 2 })); // brake disc
        // caliper hint
        const cal = E("rect", { x: cx + 12, y: 140, width: 6, height: 16, rx: 2, fill: "#e0822e", transform: `rotate(35 ${cx} 148)` });
        host.appendChild(cal);
        const sp = E("g", {}); host.appendChild(sp);
        sp.appendChild(E("circle", { cx, cy: 148, r: 21, fill: "url(#ds-rim)" }));
        for (let k = 0; k < 5; k++) {
          sp.appendChild(E("path", {
            d: `M${cx} 148 L${cx - 3.5} 129 Q${cx} 127 ${cx + 3.5} 129 Z`,
            fill: "#3a4452", transform: `rotate(${k * 72} ${cx} 148)`,
          }));
        }
        sp.appendChild(E("circle", { cx, cy: 148, r: 6.5, fill: "url(#ds-rim)", stroke: "#5b6573", "stroke-width": 1 }));
        return sp;
      }
      const spR = wheel(carSvg.querySelector(".ds-wR"), 300);
      const spF = wheel(carSvg.querySelector(".ds-wF"), 700);

      // ================= HIL instrument cluster =================
      const clu = panel.querySelector(".ds-cluster");
      clu.setAttribute("viewBox", "0 -12 1000 174");
      const NS = "http://www.w3.org/2000/svg";
      function arcGauge(cx, cy, r, label, unit, color, vmax, redFrom) {
        const G = E("g", {}); clu.appendChild(G);
        const A0 = -135, SWEEP = 270;                  // gap at bottom, sweep over the top
        const pol = (deg, rr) => [cx + rr * Math.sin(deg * Math.PI / 180), cy - rr * Math.cos(deg * Math.PI / 180)];
        const arc = (d0, d1, rr) => { const [x0, y0] = pol(d0, rr), [x1, y1] = pol(d1, rr); const large = Math.abs(d1 - d0) > 180 ? 1 : 0; return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${rr} ${rr} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
        G.appendChild(E("path", { d: arc(A0, A0 + SWEEP, r), fill: "none", stroke: "#1b2531", "stroke-width": 8, "stroke-linecap": "round" }));
        if (redFrom != null && redFrom < 1) {            // redline zone (e.g. rev limiter)
          const dR = A0 + redFrom * SWEEP;
          G.appendChild(E("path", { d: arc(dR, A0 + SWEEP, r + 7), fill: "none", stroke: "#e5484d", "stroke-width": 3.5, opacity: 0.92 }));
        }
        const valEl = E("path", { d: arc(A0, A0 + 0.01, r), fill: "none", stroke: color, "stroke-width": 8, "stroke-linecap": "round" }); G.appendChild(valEl);
        for (let k = 0; k <= 4; k++) { const d = A0 + k / 4 * SWEEP; const [x0, y0] = pol(d, r - 7), [x1, y1] = pol(d, r + 7); G.appendChild(E("line", { x1: x0, y1: y0, x2: x1, y2: y1, stroke: "#33404f", "stroke-width": 1.5 }));
          const [lx, ly] = pol(d, r + 15); G.appendChild(E("text", { x: lx, y: ly + 3, fill: "#566173", "font-size": 7.5, "text-anchor": "middle", "font-family": "var(--mono,monospace)" })).textContent = Math.round(vmax * k / 4 / (vmax >= 1000 ? 1000 : 1)) + (vmax >= 1000 ? "k" : ""); }
        const [n0x, n0y] = pol(A0, r - 11);
        const needle = E("line", { x1: cx, y1: cy, x2: n0x, y2: n0y, stroke: color, "stroke-width": 2.5, "stroke-linecap": "round" }); G.appendChild(needle);
        G.appendChild(E("circle", { cx, cy, r: 4, fill: color }));
        const dig = E("text", { x: cx, y: cy + 30, fill: "#e6edf3", "font-size": 18, "font-weight": 700, "text-anchor": "middle", "font-family": "var(--mono,monospace)" }); dig.textContent = "0"; G.appendChild(dig);
        clu.appendChild(E("text", { x: cx, y: cy + 44, fill: "#5a6675", "font-size": 9, "text-anchor": "middle", "font-family": "var(--mono,monospace)" })).textContent = unit;
        clu.appendChild(E("text", { x: cx, y: cy + r + 26, fill: "#7d8a99", "font-size": 11, "text-anchor": "middle", "font-weight": 600, "letter-spacing": ".5" })).textContent = label;
        return (v) => { const f = Math.max(0, Math.min(1, (v || 0) / vmax)); const d = A0 + f * SWEEP; valEl.setAttribute("d", arc(A0, Math.max(A0 + 0.01, d), r)); const [nx, ny] = pol(d, r - 11); needle.setAttribute("x2", nx.toFixed(1)); needle.setAttribute("y2", ny.toFixed(1)); dig.textContent = Math.round(v || 0); needle.setAttribute("stroke", (redFrom != null && f >= redFrom) ? "#e5484d" : color); };
      }
      const vcfg = result.vehicle_config || {};
      const revLim = (vcfg.engine && vcfg.engine.rev_limit_rpm) || 7000;
      const rpmMax = Math.ceil((revLim * 1.08) / 500) * 500;
      const vehMax = Math.max(120, Math.ceil(((vcfg.transmission && vcfg.transmission.kph_per_1000rpm ? vcfg.transmission.kph_per_1000rpm.slice(-1)[0] * revLim / 1000 : 160)) / 20) * 20);
      const trqMax = Math.ceil(((vcfg.engine && vcfg.engine.max_torque_nm) || 600) * 1.15 / 50) * 50;
      const gRpm = arcGauge(95, 62, 46, "ENGINE", "rpm", "#4ea3ff", rpmMax, revLim / rpmMax);
      const gVeh = arcGauge(232, 62, 46, "VEHICLE", "kph", "#3fce6a", vehMax);
      const gTrq = s.eng_trq ? arcGauge(369, 62, 46, "TORQUE", "Nm", "#e3b341", trqMax) : null;
      // pedal bar
      const pedX = 470;
      clu.appendChild(E("rect", { x: pedX, y: 20, width: 26, height: 84, rx: 4, fill: "#11161d", stroke: "#1b2531" }));
      const pedFill = E("rect", { x: pedX, y: 104, width: 26, height: 0, rx: 4, fill: "#ff8b3d" }); clu.appendChild(pedFill);
      clu.appendChild(E("text", { x: pedX + 13, y: 120, fill: "#7d8a99", "font-size": 11, "text-anchor": "middle", "font-weight": 600 })).textContent = "PEDAL";
      const pedTx = E("text", { x: pedX + 13, y: 14, fill: "#e6edf3", "font-size": 12, "text-anchor": "middle", "font-family": "var(--mono,monospace)", "font-weight": 700 }); pedTx.textContent = "0%"; clu.appendChild(pedTx);
      // gear indicator
      const gearX = 560;
      clu.appendChild(E("rect", { x: gearX, y: 26, width: 64, height: 64, rx: 8, fill: "#0c1118", stroke: "#222c38" })); // gear box
      const gearTx = E("text", { x: gearX + 32, y: 72, fill: "#79c0ff", "font-size": 40, "font-weight": 800, "text-anchor": "middle", "font-family": "var(--mono,monospace)" }); gearTx.textContent = "–"; clu.appendChild(gearTx);
      clu.appendChild(E("text", { x: gearX + 32, y: 120, fill: "#7d8a99", "font-size": 11, "text-anchor": "middle", "font-weight": 600 })).textContent = "GEAR";
      // ax / g digital
      const axX = 670;
      clu.appendChild(E("rect", { x: axX, y: 26, width: 150, height: 64, rx: 8, fill: "#0c1118", stroke: "#1b2531" }));
      const axBig = E("text", { x: axX + 75, y: 60, fill: "#e6edf3", "font-size": 26, "font-weight": 800, "text-anchor": "middle", "font-family": "var(--mono,monospace)" }); axBig.textContent = "0.00"; clu.appendChild(axBig);
      const axG = E("text", { x: axX + 75, y: 80, fill: "#4ea3ff", "font-size": 12, "text-anchor": "middle", "font-family": "var(--mono,monospace)" }); axG.textContent = "0.00 g"; clu.appendChild(axG);
      clu.appendChild(E("text", { x: axX + 75, y: 120, fill: "#7d8a99", "font-size": 11, "text-anchor": "middle", "font-weight": 600 })).textContent = "LONGITUDINAL aₓ";
      // jerk mini digital
      const jX = 850;
      clu.appendChild(E("rect", { x: jX, y: 26, width: 120, height: 64, rx: 8, fill: "#0c1118", stroke: "#1b2531" }));
      const jBig = E("text", { x: jX + 60, y: 64, fill: "#e6edf3", "font-size": 22, "font-weight": 800, "text-anchor": "middle", "font-family": "var(--mono,monospace)" }); jBig.textContent = "0"; clu.appendChild(jBig);
      clu.appendChild(E("text", { x: jX + 60, y: 120, fill: "#7d8a99", "font-size": 11, "text-anchor": "middle", "font-weight": 600 })).textContent = "JERK m/s³";

      // ================= powertrain torque-flow schematic =================
      const pt = panel.querySelector(".ds-ptrain");
      pt.setAttribute("viewBox", "0 0 1000 96");
      const nodes = [
        { x: 70, w: 150, key: "ENGINE", sub: "rpm" },
        { x: 290, w: 130, key: "CONVERTER", sub: "TCC" },
        { x: 480, w: 130, key: "GEARBOX", sub: "gear" },
        { x: 670, w: 130, key: "FINAL DRIVE", sub: "ratio" },
        { x: 850, w: 110, key: "WHEELS", sub: "kph" },
      ];
      const nodeEls = {};
      pt.appendChild(E("line", { x1: 60, y1: 48, x2: 960, y2: 48, stroke: "#1b2531", "stroke-width": 2 }));
      nodes.forEach((n, i) => {
        const box = E("rect", { x: n.x, y: 22, width: n.w, height: 52, rx: 8, fill: "#0e131a", stroke: "#22303d", "stroke-width": 1.4, class: "ds-ptn" }); pt.appendChild(box);
        pt.appendChild(E("text", { x: n.x + n.w / 2, y: 44, fill: "#cdd6e1", "font-size": 12, "font-weight": 700, "text-anchor": "middle", "letter-spacing": ".4" })).textContent = n.key;
        const v = E("text", { x: n.x + n.w / 2, y: 62, fill: "#79c0ff", "font-size": 13, "text-anchor": "middle", "font-family": "var(--mono,monospace)", "font-weight": 700 }); v.textContent = "—"; pt.appendChild(v);
        nodeEls[n.key] = { box, v };
        if (i < nodes.length - 1) { const ax2 = nodes[i + 1].x; const mx = (n.x + n.w + ax2) / 2; pt.appendChild(E("polygon", { points: `${n.x + n.w + 4},43 ${n.x + n.w + 16},48 ${n.x + n.w + 4},53`, fill: "#3a4452", class: `ds-flow f${i}` })); }
      });

      function hilUpdate(tt, rpm, vehv, trq, pedv, gearv, axv, jerkv, state, issueActive) {
        gRpm(rpm || 0); gVeh(vehv || 0); if (gTrq) gTrq(trq || 0);
        const pf = Math.max(0, Math.min(1, (pedv || 0) / 100)); pedFill.setAttribute("height", 84 * pf); pedFill.setAttribute("y", 104 - 84 * pf); pedTx.textContent = Math.round(pedv || 0) + "%";
        gearTx.textContent = (gearv == null ? "–" : (gearv <= 0 ? "N" : gearv));
        axBig.textContent = (axv >= 0 ? "+" : "") + axv.toFixed(2); axG.textContent = (axv / 9.80665).toFixed(2) + " g";
        axBig.setAttribute("fill", issueActive ? "#ff5347" : "#e6edf3");
        jBig.textContent = (jerkv >= 0 ? "+" : "") + jerkv.toFixed(0); jBig.setAttribute("fill", Math.abs(jerkv) > 30 ? "#e3b341" : "#e6edf3");
        nodeEls["ENGINE"].v.textContent = Math.round(rpm || 0);
        nodeEls["CONVERTER"].v.textContent = (s.tcc ? (val(s.tcc, tt) > 0.5 ? "LOCK" : "OPEN") : "—");
        nodeEls["GEARBOX"].v.textContent = (gearv == null ? "—" : (gearv <= 0 ? "N" : "G" + gearv));
        nodeEls["FINAL DRIVE"].v.textContent = (trq ? Math.round(trq) + "Nm" : "—");
        nodeEls["WHEELS"].v.textContent = Math.round(vehv || 0);
        // highlight the node where the fault sits (converter/gearbox during a shift issue)
        const hot = issueActive ? (state.indexOf("shift") >= 0 || state.indexOf("ENGAGE") >= 0 || state.indexOf("Fill") >= 0 ? "GEARBOX" : "CONVERTER") : null;
        Object.keys(nodeEls).forEach(k => nodeEls[k].box.setAttribute("stroke", k === hot ? "#ff5347" : "#22303d"));
        // X-ray torque-flow glow: intensity from torque / drive demand, red at a fault
        if (tflowEl) {
          const drv = Math.max(Math.min((trq || 0) / (trqMax || 600), 1), Math.max(0, (axv || 0) / 4));
          tflowEl.setAttribute("opacity", (0.12 + 0.85 * Math.max(0, Math.min(1, drv))).toFixed(2));
          tflowEl.setAttribute("stroke", issueActive ? "#ff4133" : "#ff7043");
          tflowEl.setAttribute("stroke-width", (2.5 + 2.5 * Math.max(0, Math.min(1, drv))).toFixed(1));
          if (engEls) engEls.forEach(e => e.setAttribute("stroke", issueActive ? "#ff4133" : "#3a0f08"));
        }
      }
      // HIL header refs
      const ledEl = panel.querySelector(".ds-led"), simtEl = panel.querySelector(".ds-simt"),
        rateEl = panel.querySelector(".ds-rate"), stateEl = panel.querySelector(".ds-state"),
        plantEl = panel.querySelector(".ds-plant"), cycEl = panel.querySelector(".ds-cyc");
      // X-ray powertrain refs + toggle
      const tflowEl = carSvg.querySelector(".ds-tflow"), ptEl = carSvg.querySelector(".ds-pt"),
        bodyFill = carSvg.querySelector(".ds-body-fill"),
        engEls = Array.from(carSvg.querySelectorAll('.ds-pt rect[fill="url(#ds-eng)"]'));
      const xrayBtn = panel.querySelector(".ds-xray-btn"); let xrayOn = true;
      function setXray(on) {
        xrayOn = on;
        ptEl.setAttribute("opacity", on ? 1 : 0);
        bodyFill.setAttribute("fill-opacity", on ? 0.32 : 1);
        xrayBtn.classList.toggle("ds-xray-on", on);
      }
      xrayBtn.onclick = () => setXray(!xrayOn);
      rateEl.textContent = Math.round(1 / (t[1] - t[0])) + " Hz";
      { const vc = result.vehicle_config; if (vc && vc.vehicle && vc.vehicle.name) { plantEl.textContent = vc.vehicle.name.length > 22 ? vc.vehicle.name.slice(0, 22) : vc.vehicle.name; } else if (result.file) { const fn = result.file.split(/[\\/]/).pop(); plantEl.textContent = (fn.match(/GEMT\d/) || ["GEMT6"])[0]; } }

      // ---- interaction ----

      // disturbance that is ~zero except at issue markers -> car is smooth when clean
      const issueMarks = (ev.markers || []).filter(mm => mm.severity === "bad" || mm.severity === "warn");
      const SEVA = { bad: 1.0, warn: 0.55 };
      function disturbance(tt) {
        let p = 0, h = 0, s2 = 0;
        for (const mm of issueMarks) {
          const c = (mm.t_end && mm.t_end > mm.t) ? (mm.t + mm.t_end) / 2 : mm.t;
          const d = tt - c, amp = SEVA[mm.severity] || 0;
          if (Math.abs(d) > 0.55) continue;
          const env = Math.exp(-(d * d) / (2 * 0.10 * 0.10));
          const ring = Math.sin(2 * Math.PI * (mm.f || 6) * d);
          if (mm.kind === "shuffle") { s2 += amp * env * ring * 3.2; p += amp * env * ring * 0.8; }
          else if (mm.kind === "snatch") { p -= amp * env * 2.4; h -= amp * env * 0.6; }
          else if (mm.kind === "shunt") { p += amp * env * 2.4; h += amp * env * 0.5; }
          else if (mm.kind === "shock" || mm.kind === "execution" || mm.kind === "shake") { h += amp * env * ring * 2.2; p += amp * env * ring * 1.0; }
          else if (mm.kind === "disturb") { s2 += amp * env * ring * 2.0; p += amp * env * ring * 0.6; }
        }
        return { p, h, s: s2 };
      }
      function activeIssue(tt) {
        let best = null, bd = 1e9;
        for (const mm of issueMarks) {
          const lo = mm.t - 0.12, hi = (mm.t_end || mm.t) + 0.18;
          if (tt >= lo && tt <= hi) { const d = Math.abs(tt - mm.t); if (d < bd) { bd = d; best = mm; } }
        }
        return best;
      }
      const isDown = ev.type === "kickdown_downshift";
      const LBL = {
        drive_away: "Drive-away launch", drive_away_ess: "ESS drive-away",
        accel_constant_load: "Acceleration — constant load",
        accel_load_increase: "Acceleration — load increase",
        tip_out_overrun: "Tip-out / overrun", lever_change: "Garage shift / lever change", decel_coast:"Decel (coast)",decel_brake:"Decel (brake)",tip_in_cstspd:"Tip-in cst speed",tip_out_cstspd:"Tip-out cst speed",engine_start:"Engine start",engine_stop:"Engine stop",idle:"Idle",
      };
      const phase = tt => {
        if (hasShift) {
          if (tt < ti) return ["Coast / approach", "#3fce6a"];
          if (tt < teng) return [isDown ? "Trigger → " + (m.exec_ms ?? "?") + "ms shift execution" : "Shift in progress", "#a371f7"];
          if (tt < teng + 0.22) return [isDown ? "Engaged — snatch" : "Re-engagement — shock", "#f0883e"];
          if (tt < teng + 1.05) return ["Driveline surge" + (m.fs ? " " + m.fs + " Hz" : ""), "#e3b341"];
          return ["Settled pull", "#3fce6a"];
        }
        return [tt < ti ? "Before event" : (LBL[ev.type] || "Event"), tt < ti ? "#3fce6a" : "#3b8bff"];
      };
      function update(tt) {
        cursor.setAttribute("x1", xOf(tt)); cursor.setAttribute("x2", xOf(tt));
        const a = ax(tt); axDot.setAttribute("cx", xOf(tt)); axDot.setAttribute("cy", axLane.yOf(Math.max(axLane.lo, Math.min(axLane.hi, a))));
        const aS = axBase(tt), j = (ax(tt + 0.01) - ax(tt - 0.01)) / 0.02;
        // SMOOTH baseline + (measured) marker disturbance, OR direct simulated response
        let pitch, squat, hop, surge, aDrive;
        if (simMode) {
          aDrive = axSimAt(tt); const tgt = axTgtAt(tt), ring = aDrive - tgt;
          surge = Math.max(-12, Math.min(12, ring * 3.0));
          pitch = Math.max(-5, Math.min(5, -(tgt * 0.42) - ring * 1.3));
          squat = Math.max(-1.2, Math.min(4, tgt * 0.30));
          hop = Math.max(-3, Math.min(3, ring * 1.2));
        } else {
          aDrive = aS; const dist = disturbance(tt);
          surge = Math.max(-12, Math.min(12, dist.s));
          pitch = Math.max(-5, Math.min(5, -(aS * 0.42) + dist.p));
          squat = Math.max(-1.2, Math.min(4, aS * 0.30));
          hop = Math.max(-3, Math.min(3, dist.h));
        }
        veh.setAttribute("transform", `translate(${-surge} 0)`);
        const bodyTf = `translate(0 ${squat + hop}) rotate(${pitch} 480 150)`;
        cb.setAttribute("transform", bodyTf);
        if (ptEl) ptEl.setAttribute("transform", bodyTf);
        shadow.setAttribute("rx", 270 - Math.abs(surge) * 1.5);
        // g-force vector at the CG
        const gforce = aDrive / 9.80665, cgx = 470, cgy = 92;
        const L = Math.min(150, Math.abs(gforce) * 150), dir = gforce >= 0 ? 1 : -1;
        const tip = cgx + dir * L, col = gforce >= 0 ? "#4ea3ff" : "#ff5d52";
        gvln.setAttribute("x1", cgx); gvln.setAttribute("x2", L > 5 ? tip : cgx);
        gvln.setAttribute("stroke", col);
        gvhd.setAttribute("points", L > 8 ? `${tip},${cgy - 6} ${tip + dir * 12},${cgy} ${tip},${cgy + 6}` : "");
        gvhd.setAttribute("fill", col);
        gvtx.setAttribute("x", cgx + dir * Math.max(28, L / 2)); gvtx.setAttribute("fill", col);
        gvtx.textContent = `aₓ ${gforce >= 0 ? "+" : ""}${gforce.toFixed(2)} g`;
        const ai = simMode ? null : activeIssue(tt);
        const [pl, pc] = ai ? [ai.label + (ai.f && ai.kind === "shuffle" ? " " + ai.f + " Hz" : ""), MKCOL[ai.severity]] : phase(tt);
        phaseEl.textContent = pl; phaseEl.style.color = pc; phaseEl.style.borderColor = pc;
        let rows = `<div class="ds-rt">t = <b>${tt.toFixed(2)}</b> s${ai ? ` · <span style="color:${MKCOL[ai.severity]}">▲ ${ai.label}</span>` : ""}</div>`;
        const add = (k, lbl, dec, u) => { if (s[k] == null) return; rows += `<div class="ds-r"><span><i style="background:${SIG[k].col}"></i>${lbl}</span><b>${val(s[k], tt).toFixed(dec)}${u}</b></div>`; };
        add("ax_filt", "ax", 2, ""); rows += `<div class="ds-r"><span>jerk</span><b>${j >= 0 ? "+" : ""}${j.toFixed(1)}</b></div>`;
        if (s.gear_act) rows += `<div class="ds-r"><span><i style="background:#e6edf3"></i>gear</span><b>${Math.round(val(s.gear_act, tt))}</b></div>`;
        add("engine_speed", "rpm", 0, ""); add("turbine_speed", "turb", 0, ""); add("eng_trq", "trq", 0, " Nm"); add("vehicle_speed", "veh", 0, " kph"); add("pedal", "ped", 0, "%");
        ro.innerHTML = rows;
        // ---- HIL cluster + powertrain + header ----
        simtEl.textContent = tt.toFixed(2);
        if (cycEl) cycEl.textContent = (tt - t[0]).toFixed(1);
        stateEl.textContent = (pl || "—").toUpperCase().slice(0, 22);
        stateEl.style.color = pc;
        hilUpdate(tt,
          s.engine_speed ? val(s.engine_speed, tt) : 0,
          s.vehicle_speed ? val(s.vehicle_speed, tt) : 0,
          s.eng_trq ? val(s.eng_trq, tt) : 0,
          s.pedal ? val(s.pedal, tt) : 0,
          s.gear_act ? Math.round(val(s.gear_act, tt)) : null,
          a, j, pl, !!ai);
      }
      let cur = ti - 0.3, playing = true, speed = 0.5, last = performance.now(), ang = 0;
      const playBtn = panel.querySelector(".ds-play");
      seekTo = (to) => { cur = Math.max(T0, Math.min(T1, to)); playing = false; playBtn.textContent = "Play"; playBtn.classList.remove("active"); update(cur); };
      // issue timeline strip (exact times, click to jump)
      const bar = panel.querySelector(".ds-issuebar");
      if (bar) {
        if (markers.length) {
          bar.innerHTML = `<span class="ds-ibl">Events &amp; issues:</span>`;
          markers.forEach(mm => {
            const col = MKCOL[mm.severity] || MKCOL.info;
            const chip = E("button", { class: "ds-ichip", style: `border-color:${col};color:${col}` });
            chip.innerHTML = `${mm.label} <b>${mm.t.toFixed(2)}s</b>`;
            chip.onclick = () => seekTo(mm.t);
            bar.appendChild(chip);
          });
        } else {
          bar.innerHTML = `<span class="ds-ibl ok">No discrete issues localized — clean maneuver.</span>`;
        }
      }
      function loop(now) {
        if (!panel.isConnected) return;
        const dt = (now - last) / 1000; last = now;
        if (playing) { cur += dt * speed; if (cur > T1) cur = ti - 0.3; }
        ledEl.classList.toggle("run", playing); ledEl.classList.toggle("hold", !playing);
        panel.querySelector(".ds-runtxt").textContent = playing ? "RUN" : "HOLD";
        const v = s.vehicle_speed ? val(s.vehicle_speed, cur) : 20; ang += dt * speed * v * 7;
        spR.setAttribute("transform", `rotate(${ang} 300 148)`); spF.setAttribute("transform", `rotate(${ang} 700 148)`);
        dashes.setAttribute("transform", `translate(${-(ang * 0.5) % 70} 0)`);
        update(cur); requestAnimationFrame(loop);
      }
      // ================= HIL plant calibration panel =================
      const sliderHTML = (id, label, unit, min, max, val, step) =>
        `<div class="ds-k"><label>${label}<span class="ds-kv" data-kv="${id}">${val}${unit}</span></label>
         <input type="range" class="ds-kn" data-k="${id}" min="${min}" max="${max}" value="${val}" step="${step || 1}"></div>`;
      const pp = elH("div", "ds-plant-panel");
      pp.innerHTML =
        `<div class="ds-pp-head"><b>HIL plant — what-if calibration</b>
           <span class="ds-pp-leg"><i style="background:#ff5347"></i>measured&nbsp;&nbsp;<i style="background:#22d3ee"></i>simulated</span>
           <label class="ds-pp-tog"><input type="checkbox" class="ds-pp-sim"> drive vehicle from simulation</label>
           <button class="ds-pp-reset">Reset to measured</button></div>
         <div class="ds-pp-grid">
           <div class="ds-pp-knobs">
             ${sliderHTML("rate", "Tip-in / shift torque rate", "%", 20, 200, 100)}
             ${sliderHTML("fill", "Clutch-fill time", "ms", 0, 300, 20)}
             ${sliderHTML("damp", "Active anti-shuffle damping", "%", 0, 100, 0)}
             ${sliderHTML("lash", "Lash compensation", "%", 0, 100, 30)}
           </div>
           <div class="ds-pp-out"></div>
         </div>`;
      panel.appendChild(pp);
      const out = pp.querySelector(".ds-pp-out");
      const fmtDelta = (lbl, b, now, unit) => {
        const d = b > 1e-6 ? (now - b) / b * 100 : 0;
        const col = Math.abs(d) < 1.5 ? "#7d8a99" : (now < b ? "#3fce6a" : "#ff5347");
        return `<div class="ds-pp-row"><span>${lbl}</span><b>${now.toFixed(2)}<small> ${unit}</small></b><i style="color:${col}">${d >= 0 ? "+" : ""}${d.toFixed(0)}%</i></div>`;
      };
      function refresh(live) {
        knobs = {
          rate: (+pp.querySelector('[data-k=rate]').value) / 100,
          fill: (+pp.querySelector('[data-k=fill]').value) / 1000,
          damp: (+pp.querySelector('[data-k=damp]').value) / 100,
          lash: (+pp.querySelector('[data-k=lash]').value) / 100,
        };
        pp.querySelector('[data-kv=rate]').textContent = Math.round(knobs.rate * 100) + "%";
        pp.querySelector('[data-kv=fill]').textContent = Math.round(knobs.fill * 1000) + "ms";
        pp.querySelector('[data-kv=damp]').textContent = Math.round(knobs.damp * 100) + "%";
        pp.querySelector('[data-kv=lash]').textContent = Math.round(knobs.lash * 100) + "%";
        curSim = plantSim(target, SDT, kFrom(knobs, fitGain));
        let snatch = 0; for (let i = 1; i < SN; i++) snatch = Math.max(snatch, (curSim[i] - curSim[i - 1]) / SDT);
        const shuffle = ringRMS(curSim, target);
        out.innerHTML =
          `<div class="ds-pp-ttl">Predicted response <span>vs measured baseline</span></div>` +
          fmtDelta("Snatch (Ax gradient)", baseSnatch, snatch, "m/s²/s") +
          fmtDelta("Shuffle (residual RMS)", baseShuffle, shuffle, "m/s²") +
          `<div class="ds-pp-note">Driveline mode ${fHz.toFixed(1)} Hz · 2-inertia model. Lower torque rate &amp; higher damping trade response for smoothness.` +
          ((result.vehicle_config && result.vehicle_config.vehicle) ? `<br>Plant: ${result.vehicle_config.vehicle.name} · ${result.vehicle_config.vehicle.mass_kg} kg · road-load A0 ${result.vehicle_config.vehicle.A0_N} N · ${result.vehicle_config.transmission.gears}-spd. Edit in Vehicle setup.` : "") +
          `</div>`;
        redrawSim();
        if (live) update(cur);
      }
      pp.querySelectorAll('.ds-kn').forEach(el => el.addEventListener('input', () => refresh(true)));
      pp.querySelector('.ds-pp-sim').addEventListener('change', e => { simMode = e.target.checked; redrawSim(); update(cur); });
      pp.querySelector('.ds-pp-reset').onclick = () => {
        pp.querySelector('[data-k=rate]').value = 100; pp.querySelector('[data-k=fill]').value = 20;
        pp.querySelector('[data-k=damp]').value = 0; pp.querySelector('[data-k=lash]').value = 30;
        refresh(true);
      };
      refresh(false);
      requestAnimationFrame(loop);
      function scrub(ev2) { const r = scope.getBoundingClientRect(); const x = (ev2.clientX - r.left) / r.width * SW; cur = Math.max(T0, Math.min(T1, tOf(x))); playing = false; playBtn.textContent = "Play"; playBtn.classList.remove("active"); update(cur); }
      let drag = false;
      scope.addEventListener("pointerdown", e => { drag = true; scrub(e); });
      window.addEventListener("pointermove", e => { if (drag) scrub(e); });
      window.addEventListener("pointerup", () => drag = false);
      playBtn.onclick = () => { playing = !playing; playBtn.textContent = playing ? "Pause" : "Play"; playBtn.classList.toggle("active", playing); last = performance.now(); };
      panel.querySelector(".ds-restart").onclick = () => { cur = ti - 0.3; };
      panel.querySelectorAll(".ds-spd").forEach(b => b.onclick = () => { speed = parseFloat(b.dataset.s); panel.querySelectorAll(".ds-spd").forEach(x => x.classList.remove("active")); b.classList.add("active"); });
    }
  }

  global.DriveScope = { renderApp };
})(window);
