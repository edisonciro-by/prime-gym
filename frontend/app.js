/* =====================================================================
   Prime Gym — Frontend (HTML + JavaScript sin frameworks)
   Toda la comunicación con la base de datos pasa por la API (/api/...):
   el navegador NUNCA se conecta directamente a MongoDB.
   ===================================================================== */

const API = "/api";
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const vista = $("#vista");

/* ----------------------------- Utilidades ----------------------------- */
async function api(metodo, ruta, cuerpo) {
  const op = { method: metodo, headers: { "Content-Type": "application/json" } };
  if (cuerpo !== undefined) op.body = JSON.stringify(cuerpo);
  const r = await fetch(API + ruta, op);
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}
const GET = (ruta) => api("GET", ruta);

const pesos = (n) => "$" + Math.round(n || 0).toLocaleString("es-CO");
const fecha = (iso) => (iso ? new Date(iso).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const fechaHora = (iso) => new Date(iso).toLocaleString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const isoDia = (iso) => (iso ? iso.slice(0, 10) : "");
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cap = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : "");
const qs = (obj) => {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => { if (v !== "" && v !== false && v != null) p.append(k, v); });
  const s = p.toString();
  return s ? "?" + s : "";
};
const DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"];
const TIPOS = ["yoga", "spinning", "crossfit", "funcional", "pilates", "zumba", "boxeo"];
const METODOS = ["efectivo", "tarjeta", "transferencia", "nequi"];
const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function toast(msg, tipo = "ok") {
  const d = document.createElement("div");
  d.className = "toast " + tipo;
  d.textContent = msg;
  $("#toasts").appendChild(d);
  setTimeout(() => d.remove(), tipo === "error" ? 6000 : 3500);
}

/* Envuelve una acción: si la API responde error, se muestra al usuario */
async function intentar(fn, msgOk) {
  try { const r = await fn(); if (msgOk) toast(msgOk); return r; }
  catch (e) { toast(e.message, "error"); throw e; }
}

/* ------------------------------- Modal ------------------------------- */
function abrirModal(titulo, html, ancho = false) {
  $("#modal-titulo").textContent = titulo;
  $("#modal-cuerpo").innerHTML = html;
  $(".modal").classList.toggle("ancho", ancho);
  $("#modal").classList.add("abierto");
  return $("#modal-cuerpo");
}
function cerrarModal() { $("#modal").classList.remove("abierto"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal" || e.target.dataset.cerrar !== undefined) cerrarModal(); });

/* ------------------- Constructor genérico de formularios -------------------
   campos: [{n: nombre, l: etiqueta, t: tipo, op: opciones, req, full, v: valor, ...}] */
function campoHTML(c) {
  const val = c.v ?? "";
  const req = c.req === false ? "" : "required";
  const attrs = `name="${c.n}" ${req} ${c.min != null ? `min="${c.min}"` : ""} ${c.max != null ? `max="${c.max}"` : ""} ${c.patron ? `pattern="${c.patron}"` : ""} ${c.ph ? `placeholder="${esc(c.ph)}"` : ""}`;
  let input;
  if (c.t === "select") {
    input = `<select ${attrs}>${c.vacio ? `<option value="">${c.vacio}</option>` : ""}${c.op.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(val) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
  } else if (c.t === "checkbox") {
    return `<label class="check campo ${c.full ? "full" : ""}"><input type="checkbox" name="${c.n}" ${val ? "checked" : ""}> ${c.l}</label>`;
  } else if (c.t === "multi") {
    input = `<div class="checks">${c.op.map(([v, t]) => `<label class="check"><input type="checkbox" name="${c.n}" value="${v}" ${(val || []).includes(v) ? "checked" : ""}> ${t}</label>`).join("")}</div>`;
  } else if (c.t === "textarea") {
    input = `<textarea ${attrs} rows="2">${esc(val)}</textarea>`;
  } else if (c.t === "socio") {
    input = `<div class="buscador" data-socio="${c.n}">
      <input type="search" placeholder="Escriba nombre o documento…" autocomplete="off" value="${esc(c.texto || "")}">
      <input type="hidden" name="${c.n}" value="${esc(val)}">
      <div class="sugerencias"></div></div>`;
  } else {
    input = `<input type="${c.t || "text"}" value="${esc(val)}" ${attrs} ${c.t === "number" ? 'step="any"' : ""}>`;
  }
  return `<label class="campo ${c.full ? "full" : ""}"><span>${c.l}</span>${input}</label>`;
}

function formularioHTML(campos, textoBoton = "Guardar") {
  let html = "";
  for (const c of campos) {
    if (c.grupo) html += `<fieldset><legend>${c.grupo}</legend>${c.campos.map(campoHTML).join("")}</fieldset>`;
    else html += campoHTML(c);
  }
  return `<form class="formulario">${html}<div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">${textoBoton}</button></div></form>`;
}

/* Lee el formulario y arma el objeto JSON con los tipos correctos */
function leerFormulario(form, campos) {
  const plano = campos.flatMap((c) => (c.grupo ? c.campos.map((x) => ({ ...x, grupo: c.clave })) : [c]));
  const datos = {};
  for (const c of plano) {
    let v;
    if (c.t === "checkbox") v = form.querySelector(`[name="${c.n}"]`).checked;
    else if (c.t === "multi") v = [...form.querySelectorAll(`[name="${c.n}"]:checked`)].map((x) => x.value);
    else {
      v = form.querySelector(`[name="${c.n}"]`).value.trim();
      if (c.t === "number") v = v === "" ? null : Number(v);
      if (v === "" && c.req === false) v = c.nulo ? null : "";
    }
    const destino = c.grupo ? (datos[c.grupo] ??= {}) : datos;
    destino[c.n.split(".").pop()] = v;
  }
  return datos;
}

/* Abre un modal con formulario; al enviar llama a onGuardar(datos) */
function modalFormulario(titulo, campos, onGuardar, textoBoton) {
  const cuerpo = abrirModal(titulo, formularioHTML(campos, textoBoton));
  activarBuscadoresSocio(cuerpo);
  const form = $("form", cuerpo);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const boton = form.querySelector(".primario");
    boton.disabled = true;
    try { await onGuardar(leerFormulario(form, campos)); cerrarModal(); }
    catch (err) { toast(err.message, "error"); }
    finally { boton.disabled = false; }
  });
}

/* Buscador de socios con autocompletado (consulta /api/socios?q=...) */
function activarBuscadoresSocio(raiz, alElegir) {
  raiz.querySelectorAll("[data-socio]").forEach((caja) => {
    const texto = caja.querySelector("input[type=search]");
    const oculto = caja.querySelector("input[type=hidden]");
    const lista = caja.querySelector(".sugerencias");
    texto.addEventListener("input", debounce(async () => {
      oculto.value = "";
      if (texto.value.trim().length < 2) { lista.style.display = "none"; return; }
      const r = await GET(`/socios${qs({ q: texto.value, por_pagina: 8 })}`);
      lista.innerHTML = r.datos.map((s) => `<div data-id="${s.id}" data-txt="${esc(s.nombre + " " + s.apellido)} · ${s.documento}">
        <b>${esc(s.nombre)} ${esc(s.apellido)}</b> · ${s.documento} <small>${s.membresia_activa ? "✓ " + esc(s.membresia_activa.plan) : "sin membresía"}</small></div>`).join("")
        || `<div class="vacio">Sin resultados</div>`;
      lista.style.display = "block";
    }));
    lista.addEventListener("click", (e) => {
      const d = e.target.closest("[data-id]");
      if (!d) return;
      oculto.value = d.dataset.id;
      texto.value = d.dataset.txt;
      lista.style.display = "none";
      if (alElegir) alElegir(d.dataset.id);
    });
  });
}

function tabla(columnas, filas, vacio = "No hay registros") {
  if (!filas.length) return `<div class="vacio">${vacio}</div>`;
  return `<div class="tabla-cont"><table><thead><tr>${columnas.map((c) => `<th class="${c.cls || ""}">${c.t}</th>`).join("")}</tr></thead>
    <tbody>${filas.map((f) => `<tr>${columnas.map((c) => `<td class="${c.cls || ""}">${c.f(f)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
const barra = (pct) => `<div class="barra ${pct >= 100 ? "llena" : ""}"><div style="width:${Math.min(pct, 100)}%"></div></div>`;
const chip = (estado) => `<span class="chip ${estado}">${cap(estado)}</span>`;

/* Catálogos que se usan en los formularios (sedes, planes, entrenadores) */
const cache = {};
async function catalogos(forzar = false) {
  if (!cache.sedes || forzar) {
    [cache.sedes, cache.planes, cache.entrenadores] = await Promise.all([GET("/sedes"), GET("/planes"), GET("/entrenadores")]);
  }
  return cache;
}
const opcionesSedes = (soloActivas = true) => cache.sedes.filter((s) => !soloActivas || s.activa).map((s) => [s.id, s.nombre]);

/* Gráficos (Chart.js) */
const graficos = {};
function grafico(id, config) {
  if (graficos[id]) graficos[id].destroy();
  graficos[id] = new Chart(document.getElementById(id), config);
}
Chart.defaults.font.family = "Inter, sans-serif";
Chart.defaults.color = "#6b7076";

/* ============================== VISTAS ============================== */
const vistas = {};

/* ------------------------------ Tablero ------------------------------ */
vistas.tablero = async () => {
  const [k, ingresos, horas, vencer] = await Promise.all([
    GET("/reportes/resumen"), GET("/reportes/ingresos-mensuales?meses=12"),
    GET("/reportes/horas-pico"), GET("/reportes/por-vencer?dias=7"),
  ]);
  vista.innerHTML = `
    <div class="kpis">
      <div class="kpi oscuro"><div class="etq">Ingresos del mes</div><div class="val">${pesos(k.ingresos_mes)}</div></div>
      <div class="kpi"><div class="etq">Socios</div><div class="val">${k.total_socios}</div></div>
      <div class="kpi"><div class="etq">Membresías activas</div><div class="val">${k.membresias_activas}</div></div>
      <div class="kpi"><div class="etq">Retención</div><div class="val">${k.tasa_retencion}%</div></div>
      <div class="kpi"><div class="etq">Ocupación clases</div><div class="val">${k.ocupacion_clases}%</div></div>
      <div class="kpi"><div class="etq">Cartera pendiente</div><div class="val">${pesos(k.cartera_pendiente)}</div></div>
      <div class="kpi"><div class="etq">Ingresos hoy</div><div class="val">${k.asistencias_hoy}</div></div>
    </div>
    <div class="grid2">
      <div class="panel"><h3>Ingresos por mes</h3><p class="pregunta">Pagos recibidos en los últimos 12 meses</p><canvas id="g-ingresos" height="220"></canvas></div>
      <div class="panel"><h3>Horas pico</h3><p class="pregunta">Ingresos al gimnasio por hora (últimos 90 días)</p><canvas id="g-horas" height="220"></canvas></div>
    </div>
    <div class="panel"><h3>Membresías que vencen en los próximos 7 días</h3><p class="pregunta">Socios para contactar y ofrecer renovación</p>
      ${tabla([
        { t: "Socio", f: (r) => esc(r.socio) }, { t: "Teléfono", f: (r) => r.telefono }, { t: "Sede", f: (r) => esc(r.sede) },
        { t: "Plan", f: (r) => esc(r.plan) }, { t: "Vence", f: (r) => fecha(r.fecha_fin) },
        { t: "Días", cls: "num", f: (r) => r.dias_restantes },
      ], vencer, "Ninguna membresía vence esta semana")}
    </div>`;
  grafico("g-ingresos", {
    type: "bar",
    data: { labels: ingresos.map((x) => x.periodo), datasets: [{ data: ingresos.map((x) => x.total), backgroundColor: "#5c7a00", borderRadius: 4 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => pesos(c.raw) } } },
      scales: { y: { ticks: { callback: (v) => "$" + v / 1e6 + "M" } }, x: { grid: { display: false } } } },
  });
  grafico("g-horas", {
    type: "line",
    data: { labels: horas.por_hora.map((x) => x.hora), datasets: [{ data: horas.por_hora.map((x) => x.ingresos), borderColor: "#16181d", backgroundColor: "rgba(198,242,78,.45)", fill: true, tension: .35 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } } } },
  });
};

/* ----------------------------- Recepción ----------------------------- */
vistas.recepcion = async () => {
  await catalogos();
  vista.innerHTML = `
    <div class="panel"><h3>Registrar ingreso</h3>
      <p class="pregunta">Busque al socio; el sistema valida su membresía y el acceso a la sede antes de registrar la entrada.</p>
      <div class="filtros">
        <div class="buscador" data-socio="socio_id" style="flex:1;min-width:260px">
          <input type="search" placeholder="Nombre o documento del socio…" autocomplete="off" style="width:100%">
          <input type="hidden" name="socio_id"><div class="sugerencias"></div></div>
        <select id="r-sede">${opcionesSedes().map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>
        <button class="btn acento" id="r-registrar">Registrar ingreso</button>
      </div>
      <div id="r-resultado"></div>
    </div>
    <div class="panel"><h3>Ingresos de hoy</h3><div id="r-hoy"></div></div>`;
  activarBuscadoresSocio(vista);
  const cargarHoy = async () => {
    const hoy = new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10);
    const lista = await GET(`/asistencias${qs({ fecha: hoy, sede_id: $("#r-sede").value })}`);
    $("#r-hoy").innerHTML = tabla([
      { t: "Hora", f: (r) => fechaHora(r.fecha_hora) }, { t: "Socio", f: (r) => esc(r.socio_nombre) },
      { t: "Documento", f: (r) => r.socio_documento }, { t: "Sede", f: (r) => esc(r.sede_nombre) },
    ], lista, "Aún no hay ingresos hoy en esta sede");
  };
  $("#r-sede").addEventListener("change", cargarHoy);
  $("#r-registrar").addEventListener("click", async () => {
    const socio_id = $("[name=socio_id]", vista).value;
    if (!socio_id) return toast("Seleccione un socio de la lista", "error");
    try {
      const r = await api("POST", "/asistencias", { socio_id, sede_id: $("#r-sede").value });
      $("#r-resultado").innerHTML = `<div class="bienvenida"><b>${esc(r.mensaje)}</b><br>Membresía vigente hasta ${r.vence}${r.aviso ? `<br>⚠ ${esc(r.aviso)}` : ""}</div>`;
      cargarHoy();
    } catch (e) {
      $("#r-resultado").innerHTML = `<div class="bienvenida denegado"><b>${esc(e.message)}</b></div>`;
    }
  });
  cargarHoy();
};

/* ------------------------------- Socios ------------------------------- */
const estadoSocios = { q: "", sede_id: "", estado: "", pagina: 1 };

const camposSocio = (s = {}) => [
  { n: "documento", l: "Documento", v: s.documento, patron: "\\d{6,12}", ph: "Solo números" },
  { n: "email", l: "Correo", t: "email", v: s.email },
  { n: "nombre", l: "Nombres", v: s.nombre },
  { n: "apellido", l: "Apellidos", v: s.apellido },
  { n: "fecha_nacimiento", l: "Fecha de nacimiento", t: "date", v: isoDia(s.fecha_nacimiento) },
  { n: "genero", l: "Género", t: "select", v: s.genero, op: [["M", "Masculino"], ["F", "Femenino"], ["O", "Otro"]] },
  { n: "telefono", l: "Celular", v: s.telefono, patron: "3\\d{9}", ph: "3001234567" },
  { n: "sede_id", l: "Sede principal", t: "select", v: s.sede_id, op: opcionesSedes() },
  { grupo: "Contacto de emergencia", clave: "contacto_emergencia", campos: [
    { n: "ce.nombre", l: "Nombre", v: s.contacto_emergencia?.nombre },
    { n: "ce.telefono", l: "Teléfono", v: s.contacto_emergencia?.telefono, patron: "\\d{7,10}" },
    { n: "ce.parentesco", l: "Parentesco", v: s.contacto_emergencia?.parentesco },
  ] },
];

vistas.socios = async () => {
  await catalogos();
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Nuevo socio</button>`;
  $("#nuevo").onclick = () => modalFormulario("Nuevo socio", camposSocio(), async (d) => {
    await intentar(() => api("POST", "/socios", d), "Socio creado");
    cargarSocios();
  });
  vista.innerHTML = `<div class="panel">
    <div class="filtros">
      <input type="search" id="f-q" placeholder="Buscar por nombre, apellido o documento…" value="${esc(estadoSocios.q)}">
      <select id="f-sede"><option value="">Todas las sedes</option>${opcionesSedes(false).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>
      <select id="f-estado"><option value="">Cualquier estado</option><option value="activa">Con membresía activa</option><option value="sin_membresia">Sin membresía activa</option></select>
    </div><div id="lista"></div></div>`;
  $("#f-sede").value = estadoSocios.sede_id;
  $("#f-estado").value = estadoSocios.estado;
  $("#f-q").addEventListener("input", debounce((e) => { estadoSocios.q = e.target.value; estadoSocios.pagina = 1; cargarSocios(); }));
  $("#f-sede").onchange = (e) => { estadoSocios.sede_id = e.target.value; estadoSocios.pagina = 1; cargarSocios(); };
  $("#f-estado").onchange = (e) => { estadoSocios.estado = e.target.value; estadoSocios.pagina = 1; cargarSocios(); };
  cargarSocios();
};

async function cargarSocios() {
  const r = await GET(`/socios${qs({ ...estadoSocios, por_pagina: 15 })}`);
  const paginas = Math.max(1, Math.ceil(r.total / r.por_pagina));
  $("#lista").innerHTML = tabla([
    { t: "Documento", f: (s) => s.documento },
    { t: "Nombre", f: (s) => `<b>${esc(s.nombre)} ${esc(s.apellido)}</b><br><small>${esc(s.email)}</small>` },
    { t: "Sede", f: (s) => esc(s.sede_nombre) },
    { t: "Membresía", f: (s) => (s.membresia_activa ? `${chip("activa")} ${esc(s.membresia_activa.plan)}<br><small>hasta ${fecha(s.membresia_activa.fecha_fin)}</small>` : `<span class="chip">Sin membresía</span>`) },
    { t: "", cls: "acciones", f: (s) => `<button class="btn mini" data-ver="${s.id}">Ver ficha</button><button class="btn mini" data-editar="${s.id}">Editar</button><button class="btn mini peligro" data-borrar="${s.id}">Eliminar</button>` },
  ], r.datos, "No se encontraron socios") + `<div class="paginacion"><span>${r.total} socios · página ${r.pagina} de ${paginas}</span>
    <span><button class="btn mini" id="ant" ${r.pagina <= 1 ? "disabled" : ""}>← Anterior</button> <button class="btn mini" id="sig" ${r.pagina >= paginas ? "disabled" : ""}>Siguiente →</button></span></div>`;
  $("#ant").onclick = () => { estadoSocios.pagina--; cargarSocios(); };
  $("#sig").onclick = () => { estadoSocios.pagina++; cargarSocios(); };
  $("#lista").onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.ver) fichaSocio(b.dataset.ver);
    if (b.dataset.editar) {
      const s = await GET(`/socios/${b.dataset.editar}`);
      modalFormulario("Editar socio", camposSocio(s), async (d) => {
        await intentar(() => api("PUT", `/socios/${s.id}`, d), "Socio actualizado");
        cargarSocios();
      });
    }
    if (b.dataset.borrar && confirm("¿Eliminar este socio? También se borrará su historial de membresías y asistencias.")) {
      await intentar(() => api("DELETE", `/socios/${b.dataset.borrar}`), "Socio eliminado").catch(() => {});
      cargarSocios();
    }
  };
}

async function fichaSocio(id) {
  const s = await GET(`/socios/${id}`);
  const evals = [...s.evaluaciones].sort((a, b) => b.fecha.localeCompare(a.fecha));
  const cuerpo = abrirModal(`${s.nombre} ${s.apellido}`, `<div class="ficha">
    <dl>
      <dt>Documento</dt><dd>${s.documento}</dd>
      <dt>Contacto</dt><dd>${esc(s.email)} · ${s.telefono}</dd>
      <dt>Sede principal</dt><dd>${esc(s.sede_nombre)}</dd>
      <dt>Nacimiento</dt><dd>${fecha(s.fecha_nacimiento)}</dd>
      <dt>Registrado desde</dt><dd>${fecha(s.fecha_registro)}</dd>
      <dt>Emergencia</dt><dd>${esc(s.contacto_emergencia.nombre)} (${esc(s.contacto_emergencia.parentesco)}) · ${s.contacto_emergencia.telefono}</dd>
    </dl>
    <h4>Membresías</h4>${tabla([
      { t: "Plan", f: (m) => esc(m.plan) }, { t: "Estado", f: (m) => chip(m.estado) },
      { t: "Inicio", f: (m) => fecha(m.fecha_inicio) }, { t: "Fin", f: (m) => fecha(m.fecha_fin) },
      { t: "Saldo", cls: "num", f: (m) => pesos(m.saldo_pendiente) },
    ], s.membresias, "Sin membresías")}
    <h4>Clases inscritas</h4>${tabla([
      { t: "Clase", f: (c) => esc(c.nombre) }, { t: "Día", f: (c) => cap(c.dia_semana) }, { t: "Horario", f: (c) => `${c.hora_inicio} – ${c.hora_fin}` },
    ], s.clases, "No está inscrito en clases")}
    <h4>Evaluaciones físicas</h4>${tabla([
      { t: "Fecha", f: (v) => fecha(v.fecha) }, { t: "Peso", cls: "num", f: (v) => v.peso_kg + " kg" },
      { t: "Estatura", cls: "num", f: (v) => v.estatura_cm + " cm" }, { t: "IMC", cls: "num", f: (v) => v.imc },
      { t: "% grasa", cls: "num", f: (v) => v.porcentaje_grasa ?? "—" },
      { t: "", cls: "acciones", f: (v) => `<button class="btn mini peligro" data-borrar-eval="${v.id}">Quitar</button>` },
    ], evals, "Sin evaluaciones")}
    <div style="margin-top:10px"><button class="btn" id="nueva-eval">+ Agregar evaluación</button></div>
  </div>`, true);
  cuerpo.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.id === "nueva-eval") {
      modalFormulario("Nueva evaluación física", [
        { n: "fecha", l: "Fecha", t: "date", req: false, nulo: true },
        { n: "peso_kg", l: "Peso (kg)", t: "number", min: 30, max: 300 },
        { n: "estatura_cm", l: "Estatura (cm)", t: "number", min: 100, max: 250 },
        { n: "porcentaje_grasa", l: "% de grasa", t: "number", req: false, nulo: true, min: 3, max: 70 },
        { n: "observaciones", l: "Observaciones", t: "textarea", req: false, full: true },
      ], async (d) => {
        await intentar(() => api("POST", `/socios/${id}/evaluaciones`, d), "Evaluación registrada");
        setTimeout(() => fichaSocio(id), 50);
      });
    }
    if (b.dataset.borrarEval && confirm("¿Quitar esta evaluación?")) {
      await intentar(() => api("DELETE", `/socios/${id}/evaluaciones/${b.dataset.borrarEval}`), "Evaluación eliminada");
      fichaSocio(id);
    }
  };
}

/* ----------------------------- Membresías ----------------------------- */
const estadoMem = { estado: "activa", plan_id: "", q: "", con_saldo: false };

vistas.membresias = async () => {
  await catalogos();
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Vender membresía</button>`;
  $("#nuevo").onclick = nuevaMembresia;
  vista.innerHTML = `<div class="panel"><div class="filtros">
      <input type="search" id="f-q" placeholder="Buscar socio por nombre o documento…" value="${esc(estadoMem.q)}">
      <select id="f-estado"><option value="">Todos los estados</option><option value="activa">Activas</option><option value="vencida">Vencidas</option><option value="cancelada">Canceladas</option></select>
      <select id="f-plan"><option value="">Todos los planes</option>${cache.planes.map((p) => `<option value="${p.id}">${esc(p.nombre)}</option>`).join("")}</select>
      <label class="check"><input type="checkbox" id="f-saldo"> Solo con saldo pendiente</label>
    </div><div id="lista"></div></div>`;
  $("#f-estado").value = estadoMem.estado;
  $("#f-plan").value = estadoMem.plan_id;
  $("#f-saldo").checked = estadoMem.con_saldo;
  $("#f-q").addEventListener("input", debounce((e) => { estadoMem.q = e.target.value; cargarMembresias(); }));
  $("#f-estado").onchange = (e) => { estadoMem.estado = e.target.value; cargarMembresias(); };
  $("#f-plan").onchange = (e) => { estadoMem.plan_id = e.target.value; cargarMembresias(); };
  $("#f-saldo").onchange = (e) => { estadoMem.con_saldo = e.target.checked; cargarMembresias(); };
  cargarMembresias();
};

async function cargarMembresias() {
  const lista = await GET(`/membresias${qs({ ...estadoMem, limite: 100 })}`);
  $("#lista").innerHTML = `<p class="pregunta">Mostrando ${lista.length} membresías (máx. 100)</p>` + tabla([
    { t: "Socio", f: (m) => `<b>${esc(m.socio_nombre)}</b><br><small>${m.socio_documento} · ${esc(m.sede_nombre)}</small>` },
    { t: "Plan", f: (m) => esc(m.plan_nombre) },
    { t: "Vigencia", f: (m) => `${fecha(m.fecha_inicio)} → ${fecha(m.fecha_fin)}` },
    { t: "Estado", f: (m) => chip(m.estado) },
    { t: "Precio", cls: "num", f: (m) => pesos(m.precio_total) },
    { t: "Saldo", cls: "num", f: (m) => (m.saldo_pendiente > 0 ? `<b style="color:var(--peligro)">${pesos(m.saldo_pendiente)}</b>` : pesos(0)) },
    { t: "", cls: "acciones", f: (m) => `<button class="btn mini" data-pagos="${m.id}">Pagos</button>${m.estado === "activa" ? `<button class="btn mini peligro" data-cancelar="${m.id}">Cancelar</button>` : ""}${!m.pagos.length ? `<button class="btn mini peligro" data-borrar="${m.id}">Eliminar</button>` : ""}` },
  ], lista, "No hay membresías con esos filtros");
  $("#lista").onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.pagos) verPagos(b.dataset.pagos);
    if (b.dataset.cancelar && confirm("¿Cancelar esta membresía? El socio también saldrá de sus clases.")) {
      await intentar(() => api("PUT", `/membresias/${b.dataset.cancelar}/cancelar`), "Membresía cancelada");
      cargarMembresias();
    }
    if (b.dataset.borrar && confirm("¿Eliminar esta membresía sin pagos?")) {
      await intentar(() => api("DELETE", `/membresias/${b.dataset.borrar}`), "Membresía eliminada");
      cargarMembresias();
    }
  };
}

function nuevaMembresia() {
  const hoy = new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10);
  const planesActivos = cache.planes.filter((p) => p.activo);
  const campos = [
    { n: "socio_id", l: "Socio", t: "socio", full: true },
    { n: "plan_id", l: "Plan", t: "select", op: planesActivos.map((p) => [p.id, `${p.nombre} — ${pesos(p.precio)} / ${p.duracion_dias} días`]), full: true },
    { n: "fecha_inicio", l: "Fecha de inicio", t: "date", v: hoy },
    { n: "abono", l: "Pago inicial (opcional)", t: "number", req: false, nulo: true, min: 0 },
    { n: "metodo", l: "Método de pago", t: "select", op: METODOS.map((m) => [m, cap(m)]) },
  ];
  modalFormulario("Vender membresía", campos, async (d) => {
    if (!d.socio_id) throw new Error("Seleccione un socio de la lista");
    const cuerpo = { socio_id: d.socio_id, plan_id: d.plan_id, fecha_inicio: d.fecha_inicio };
    if (d.abono) cuerpo.pago_inicial = { valor: d.abono, metodo: d.metodo };
    await intentar(() => api("POST", "/membresias", cuerpo), "Membresía registrada");
    cargarMembresias();
  }, "Registrar venta");
}

async function verPagos(id) {
  const m = await GET(`/membresias/${id}`);
  const cuerpo = abrirModal("Pagos de la membresía", `<div class="ficha">
    <dl><dt>Socio</dt><dd>${esc(m.socio_nombre)}</dd><dt>Plan</dt><dd>${esc(m.plan_nombre)} ${chip(m.estado)}</dd>
    <dt>Precio</dt><dd>${pesos(m.precio_total)}</dd><dt>Pagado</dt><dd>${pesos(m.total_pagado)}</dd>
    <dt>Saldo</dt><dd><b>${pesos(m.saldo_pendiente)}</b></dd></dl>
    ${tabla([{ t: "Fecha", f: (p) => fechaHora(p.fecha) }, { t: "Método", f: (p) => cap(p.metodo) }, { t: "Valor", cls: "num", f: (p) => pesos(p.valor) }], m.pagos, "Sin pagos registrados")}
    ${m.saldo_pendiente > 0 && m.estado !== "cancelada" ? `<form class="filtros" id="f-pago" style="margin-top:14px">
      <input type="number" name="valor" placeholder="Valor del abono" min="1" max="${m.saldo_pendiente}" required>
      <select name="metodo">${METODOS.map((x) => `<option value="${x}">${cap(x)}</option>`).join("")}</select>
      <button class="btn acento">Registrar pago</button></form>` : ""}
  </div>`);
  const f = $("#f-pago", cuerpo);
  if (f) f.onsubmit = async (e) => {
    e.preventDefault();
    await intentar(() => api("POST", `/membresias/${id}/pagos`, { valor: Number(f.valor.value), metodo: f.metodo.value }), "Pago registrado").catch(() => {});
    verPagos(id);
    cargarMembresias();
  };
}

/* ------------------------------- Clases ------------------------------- */
const estadoClases = { sede_id: "", dia: "", tipo: "", con_cupo: false, q: "" };

const camposClase = (c = {}) => [
  { n: "nombre", l: "Nombre", v: c.nombre, full: true },
  { n: "tipo", l: "Tipo", t: "select", v: c.tipo, op: TIPOS.map((t) => [t, cap(t)]) },
  { n: "sede_id", l: "Sede", t: "select", v: c.sede_id, op: opcionesSedes() },
  { n: "entrenador_id", l: "Entrenador", t: "select", v: c.entrenador_id, full: true,
    op: cache.entrenadores.filter((e) => e.activo).map((e) => [e.id, `${e.nombre} — ${e.sede_nombre} (${e.especialidades.join(", ")})`]) },
  { n: "dia_semana", l: "Día", t: "select", v: c.dia_semana, op: DIAS.map((d) => [d, cap(d)]) },
  { n: "cupo_maximo", l: "Cupo máximo", t: "number", v: c.cupo_maximo ?? 15, min: 1, max: 50 },
  { n: "hora_inicio", l: "Hora inicio", t: "time", v: c.hora_inicio || "18:00" },
  { n: "hora_fin", l: "Hora fin", t: "time", v: c.hora_fin || "19:00" },
  { n: "activa", l: "Clase activa", t: "checkbox", v: c.activa ?? true, full: true },
];

vistas.clases = async () => {
  await catalogos(true);
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Nueva clase</button>`;
  $("#nuevo").onclick = () => modalFormulario("Nueva clase", camposClase(), async (d) => {
    await intentar(() => api("POST", "/clases", d), "Clase creada");
    cargarClases();
  });
  vista.innerHTML = `<div class="panel"><div class="filtros">
      <input type="search" id="f-q" placeholder="Buscar clase…">
      <select id="f-sede"><option value="">Todas las sedes</option>${opcionesSedes(false).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>
      <select id="f-dia"><option value="">Todos los días</option>${DIAS.map((d) => `<option value="${d}">${cap(d)}</option>`).join("")}</select>
      <select id="f-tipo"><option value="">Todos los tipos</option>${TIPOS.map((t) => `<option value="${t}">${cap(t)}</option>`).join("")}</select>
      <label class="check"><input type="checkbox" id="f-cupo"> Solo con cupos</label>
    </div><div id="lista"></div></div>`;
  ["sede", "dia", "tipo"].forEach((k) => { $(`#f-${k}`).onchange = (e) => { estadoClases[k === "sede" ? "sede_id" : k] = e.target.value; cargarClases(); }; });
  $("#f-cupo").onchange = (e) => { estadoClases.con_cupo = e.target.checked; cargarClases(); };
  $("#f-q").addEventListener("input", debounce((e) => { estadoClases.q = e.target.value; cargarClases(); }));
  cargarClases();
};

async function cargarClases() {
  const lista = await GET(`/clases${qs(estadoClases)}`);
  $("#lista").innerHTML = tabla([
    { t: "Clase", f: (c) => `<b>${esc(c.nombre)}</b><br><small>${cap(c.tipo)}${c.activa ? "" : " · inactiva"}</small>` },
    { t: "Horario", f: (c) => `${cap(c.dia_semana)}<br><small>${c.hora_inicio} – ${c.hora_fin}</small>` },
    { t: "Sede", f: (c) => esc(c.sede_nombre) },
    { t: "Entrenador", f: (c) => esc(c.entrenador_nombre) },
    { t: "Ocupación", f: (c) => `${c.total_inscritos}/${c.cupo_maximo}${barra((c.total_inscritos / c.cupo_maximo) * 100)}` },
    { t: "", cls: "acciones", f: (c) => `<button class="btn mini" data-inscritos="${c.id}">Inscritos</button><button class="btn mini" data-editar="${c.id}">Editar</button><button class="btn mini peligro" data-borrar="${c.id}">Eliminar</button>` },
  ], lista, "No hay clases con esos filtros");
  $("#lista").onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.inscritos) verInscritos(b.dataset.inscritos);
    if (b.dataset.editar) {
      const c = await GET(`/clases/${b.dataset.editar}`);
      modalFormulario("Editar clase", camposClase(c), async (d) => {
        await intentar(() => api("PUT", `/clases/${c.id}`, d), "Clase actualizada");
        cargarClases();
      });
    }
    if (b.dataset.borrar && confirm("¿Eliminar esta clase?")) {
      await intentar(() => api("DELETE", `/clases/${b.dataset.borrar}`), "Clase eliminada").catch(() => {});
      cargarClases();
    }
  };
}

async function verInscritos(id) {
  const c = await GET(`/clases/${id}`);
  const cuerpo = abrirModal(`${c.nombre} · ${cap(c.dia_semana)} ${c.hora_inicio}`, `
    <p class="pregunta">${esc(c.sede_nombre)} · ${esc(c.entrenador_nombre)} · ${c.total_inscritos} de ${c.cupo_maximo} cupos</p>
    <div class="filtros">
      <div class="buscador" data-socio="socio_id" style="flex:1"><input type="search" placeholder="Buscar socio para inscribir…" autocomplete="off" style="width:100%"><input type="hidden" name="socio_id"><div class="sugerencias"></div></div>
      <button class="btn acento" id="inscribir">Inscribir</button>
    </div>
    ${tabla([{ t: "Socio", f: (s) => esc(s.nombre) }, { t: "Documento", f: (s) => s.documento },
      { t: "", cls: "acciones", f: (s) => `<button class="btn mini peligro" data-retirar="${s.socio_id}">Retirar</button>` }], c.inscritos_detalle, "Nadie inscrito todavía")}`, true);
  activarBuscadoresSocio(cuerpo);
  $("#inscribir", cuerpo).onclick = async () => {
    const socio_id = $("[name=socio_id]", cuerpo).value;
    if (!socio_id) return toast("Seleccione un socio de la lista", "error");
    try { await intentar(() => api("POST", `/clases/${id}/inscripciones`, { socio_id }), "Socio inscrito"); verInscritos(id); cargarClases(); } catch {}
  };
  cuerpo.querySelectorAll("[data-retirar]").forEach((b) => (b.onclick = async () => {
    await intentar(() => api("DELETE", `/clases/${id}/inscripciones/${b.dataset.retirar}`), "Socio retirado");
    verInscritos(id); cargarClases();
  }));
}

/* ---------------------------- Entrenadores ---------------------------- */
const camposEntrenador = (e = {}) => [
  { n: "documento", l: "Documento", v: e.documento, patron: "\\d{6,12}" },
  { n: "nombre", l: "Nombre completo", v: e.nombre },
  { n: "telefono", l: "Celular", v: e.telefono, patron: "3\\d{9}" },
  { n: "email", l: "Correo", t: "email", v: e.email },
  { n: "sede_id", l: "Sede", t: "select", v: e.sede_id, op: opcionesSedes(), full: true },
  { n: "especialidades", l: "Especialidades", t: "multi", v: e.especialidades, op: TIPOS.map((t) => [t, cap(t)]), full: true },
  { n: "activo", l: "Activo", t: "checkbox", v: e.activo ?? true, full: true },
];

vistas.entrenadores = async () => {
  await catalogos();
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Nuevo entrenador</button>`;
  $("#nuevo").onclick = () => modalFormulario("Nuevo entrenador", camposEntrenador(), async (d) => {
    await intentar(() => api("POST", "/entrenadores", d), "Entrenador creado");
    cargarEntrenadores();
  });
  vista.innerHTML = `<div class="panel"><div class="filtros">
    <input type="search" id="f-q" placeholder="Buscar por nombre o documento…">
    <select id="f-sede"><option value="">Todas las sedes</option>${opcionesSedes(false).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>
    <select id="f-esp"><option value="">Cualquier especialidad</option>${TIPOS.map((t) => `<option value="${t}">${cap(t)}</option>`).join("")}</select>
  </div><div id="lista"></div></div>`;
  const filtros = {};
  const recargar = () => cargarEntrenadores(filtros);
  $("#f-q").addEventListener("input", debounce((e) => { filtros.q = e.target.value; recargar(); }));
  $("#f-sede").onchange = (e) => { filtros.sede_id = e.target.value; recargar(); };
  $("#f-esp").onchange = (e) => { filtros.especialidad = e.target.value; recargar(); };
  recargar();
};

async function cargarEntrenadores(filtros = {}) {
  const lista = await GET(`/entrenadores${qs(filtros)}`);
  $("#lista").innerHTML = tabla([
    { t: "Nombre", f: (e) => `<b>${esc(e.nombre)}</b><br><small>${e.documento}</small>` },
    { t: "Contacto", f: (e) => `${e.telefono}<br><small>${esc(e.email)}</small>` },
    { t: "Sede", f: (e) => esc(e.sede_nombre) },
    { t: "Especialidades", f: (e) => e.especialidades.map((x) => `<span class="chip">${cap(x)}</span>`).join(" ") },
    { t: "Clases", cls: "num", f: (e) => e.total_clases },
    { t: "Estado", f: (e) => (e.activo ? chip("activa").replace("Activa", "Activo") : `<span class="chip">Inactivo</span>`) },
    { t: "", cls: "acciones", f: (e) => `<button class="btn mini" data-editar="${e.id}">Editar</button><button class="btn mini peligro" data-borrar="${e.id}">Eliminar</button>` },
  ], lista);
  $("#lista").onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.editar) {
      const e = await GET(`/entrenadores/${b.dataset.editar}`);
      modalFormulario("Editar entrenador", camposEntrenador(e), async (d) => {
        await intentar(() => api("PUT", `/entrenadores/${e.id}`, d), "Entrenador actualizado");
        cache.sedes = null; cargarEntrenadores(filtros);
      });
    }
    if (b.dataset.borrar && confirm("¿Eliminar este entrenador?")) {
      await intentar(() => api("DELETE", `/entrenadores/${b.dataset.borrar}`), "Entrenador eliminado").catch(() => {});
      cache.sedes = null; cargarEntrenadores(filtros);
    }
  };
}

/* ------------------------------- Planes ------------------------------- */
const camposPlan = (p = {}) => [
  { n: "nombre", l: "Nombre", v: p.nombre },
  { n: "precio", l: "Precio (COP)", t: "number", v: p.precio, min: 1 },
  { n: "duracion_dias", l: "Duración (días)", t: "number", v: p.duracion_dias ?? 30, min: 1, max: 365 },
  { n: "descripcion", l: "Descripción", t: "textarea", v: p.descripcion, req: false, full: true },
  { n: "incluye_clases", l: "Incluye clases grupales", t: "checkbox", v: p.incluye_clases },
  { n: "acceso_todas_sedes", l: "Acceso a todas las sedes", t: "checkbox", v: p.acceso_todas_sedes },
  { n: "activo", l: "Plan activo (disponible para la venta)", t: "checkbox", v: p.activo ?? true, full: true },
];

vistas.planes = async () => {
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Nuevo plan</button>`;
  $("#nuevo").onclick = () => modalFormulario("Nuevo plan", camposPlan(), async (d) => {
    await intentar(() => api("POST", "/planes", d), "Plan creado");
    cache.sedes = null; vistas.planes();
  });
  const lista = await GET("/planes");
  vista.innerHTML = `<div class="panel">${tabla([
    { t: "Plan", f: (p) => `<b>${esc(p.nombre)}</b><br><small>${esc(p.descripcion)}</small>` },
    { t: "Precio", cls: "num", f: (p) => pesos(p.precio) },
    { t: "Duración", cls: "num", f: (p) => p.duracion_dias + " días" },
    { t: "Clases", f: (p) => (p.incluye_clases ? "✓" : "—") },
    { t: "Todas las sedes", f: (p) => (p.acceso_todas_sedes ? "✓" : "—") },
    { t: "Estado", f: (p) => (p.activo ? chip("activa").replace("Activa", "Activo") : `<span class="chip">Inactivo</span>`) },
    { t: "", cls: "acciones", f: (p) => `<button class="btn mini" data-editar="${p.id}">Editar</button><button class="btn mini peligro" data-borrar="${p.id}">Eliminar</button>` },
  ], lista)}</div>`;
  vista.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.editar) {
      const p = lista.find((x) => x.id === b.dataset.editar);
      modalFormulario("Editar plan", camposPlan(p), async (d) => {
        await intentar(() => api("PUT", `/planes/${p.id}`, d), "Plan actualizado");
        cache.sedes = null; vistas.planes();
      });
    }
    if (b.dataset.borrar && confirm("¿Eliminar este plan?")) {
      await intentar(() => api("DELETE", `/planes/${b.dataset.borrar}`), "Plan eliminado").catch(() => {});
      cache.sedes = null; vistas.planes();
    }
  };
};

/* -------------------------------- Sedes -------------------------------- */
const camposSede = (s = {}) => [
  { n: "nombre", l: "Nombre", v: s.nombre },
  { n: "ciudad", l: "Ciudad", v: s.ciudad },
  { n: "direccion", l: "Dirección", v: s.direccion, full: true },
  { n: "telefono", l: "Teléfono", v: s.telefono, patron: "\\d{7,10}" },
  { n: "capacidad_maxima", l: "Capacidad máxima de socios", t: "number", v: s.capacidad_maxima ?? 100, min: 20 },
  { n: "activa", l: "Sede activa", t: "checkbox", v: s.activa ?? true, full: true },
];

vistas.sedes = async () => {
  $("#acciones").innerHTML = `<button class="btn primario" id="nuevo">+ Nueva sede</button>`;
  $("#nuevo").onclick = () => modalFormulario("Nueva sede", camposSede(), async (d) => {
    await intentar(() => api("POST", "/sedes", d), "Sede creada");
    cache.sedes = null; vistas.sedes();
  });
  const lista = await GET("/sedes");
  vista.innerHTML = `<div class="panel">${tabla([
    { t: "Sede", f: (s) => `<b>${esc(s.nombre)}</b><br><small>${esc(s.direccion)}</small>` },
    { t: "Ciudad", f: (s) => esc(s.ciudad) }, { t: "Teléfono", f: (s) => s.telefono },
    { t: "Socios / capacidad", f: (s) => `${s.total_socios} / ${s.capacidad_maxima}${barra((s.total_socios / s.capacidad_maxima) * 100)}` },
    { t: "Estado", f: (s) => (s.activa ? chip("activa") : `<span class="chip">Inactiva</span>`) },
    { t: "", cls: "acciones", f: (s) => `<button class="btn mini" data-editar="${s.id}">Editar</button><button class="btn mini peligro" data-borrar="${s.id}">Eliminar</button>` },
  ], lista)}</div>`;
  vista.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.editar) {
      const s = lista.find((x) => x.id === b.dataset.editar);
      modalFormulario("Editar sede", camposSede(s), async (d) => {
        await intentar(() => api("PUT", `/sedes/${s.id}`, d), "Sede actualizada");
        cache.sedes = null; vistas.sedes();
      });
    }
    if (b.dataset.borrar && confirm("¿Eliminar esta sede?")) {
      await intentar(() => api("DELETE", `/sedes/${b.dataset.borrar}`), "Sede eliminada").catch(() => {});
      cache.sedes = null; vistas.sedes();
    }
  };
};

/* ------------------------------ Reportes ------------------------------ */
vistas.reportes = async () => {
  const [planes, ocupacion, cartera, ranking, sedes, ingresos, horas] = await Promise.all([
    GET("/reportes/planes-populares"), GET("/reportes/ocupacion-clases?limite=12"), GET("/reportes/cartera?limite=15"),
    GET("/reportes/ranking-entrenadores"), GET("/reportes/sedes"), GET("/reportes/ingresos-mensuales?meses=6"), GET("/reportes/horas-pico"),
  ]);
  vista.innerHTML = `
    <div class="grid2">
      <div class="panel"><h3>1 · Planes más vendidos</h3><p class="pregunta">¿Qué planes se venden más? → ajustar precios y enfocar publicidad</p><canvas id="g-planes" height="240"></canvas></div>
      <div class="panel"><h3>2 · Ingresos por método de pago</h3><p class="pregunta">¿Cómo pagan los socios? → negociar comisiones y medios de pago</p><canvas id="g-metodos" height="240"></canvas></div>
    </div>
    <div class="panel"><h3>3 · Desempeño por sede</h3><p class="pregunta">¿Qué sede genera más ingresos y retiene más socios? → dónde invertir</p>
      ${tabla([{ t: "Sede", f: (s) => esc(s.sede) }, { t: "Ciudad", f: (s) => esc(s.ciudad) },
        { t: "Socios con historial", cls: "num", f: (s) => s.socios_con_historial }, { t: "Membresías activas", cls: "num", f: (s) => s.activas },
        { t: "Total recaudado", cls: "num", f: (s) => pesos(s.recaudado) }], sedes)}</div>
    <div class="panel"><h3>4 · Ocupación de clases</h3><p class="pregunta">¿Qué clases están llenas o vacías? → abrir horarios nuevos o cerrar los poco usados</p>
      ${tabla([{ t: "Clase", f: (c) => esc(c.nombre) }, { t: "Horario", f: (c) => `${cap(c.dia_semana)} ${c.hora_inicio}` },
        { t: "Sede", f: (c) => esc(c.sede) }, { t: "Entrenador", f: (c) => esc(c.entrenador) },
        { t: "Inscritos", cls: "num", f: (c) => `${c.inscritos}/${c.cupo_maximo}` }, { t: "Ocupación", f: (c) => `${c.ocupacion}% ${barra(c.ocupacion)}` }], ocupacion)}</div>
    <div class="grid2">
      <div class="panel"><h3>5 · Ranking de entrenadores</h3><p class="pregunta">¿Quién atrae más socios? → bonificaciones y asignación de clases</p>
        ${tabla([{ t: "Entrenador", f: (r) => `<b>${esc(r.entrenador)}</b><br><small>${esc(r.sede)}</small>` }, { t: "Clases", cls: "num", f: (r) => r.clases },
          { t: "Inscritos", cls: "num", f: (r) => r.inscritos }, { t: "Ocupación", cls: "num", f: (r) => r.ocupacion + "%" }], ranking)}</div>
      <div class="panel"><h3>6 · Días con más afluencia</h3><p class="pregunta">¿Qué días se llena el gimnasio? → turnos de personal y mantenimiento</p><canvas id="g-dias" height="260"></canvas></div>
    </div>
    <div class="panel"><h3>7 · Cartera pendiente</h3><p class="pregunta">¿Quién debe dinero? → gestión de cobro</p>
      ${tabla([{ t: "Socio", f: (c) => `<b>${esc(c.socio)}</b><br><small>${c.documento}</small>` }, { t: "Teléfono", f: (c) => c.telefono },
        { t: "Plan", f: (c) => esc(c.plan) }, { t: "Estado", f: (c) => chip(c.estado) }, { t: "Pagado", f: (c) => `${c.porcentaje_pagado}% ${barra(c.porcentaje_pagado)}` },
        { t: "Saldo", cls: "num", f: (c) => `<b>${pesos(c.saldo_pendiente)}</b>` }], cartera, "No hay saldos pendientes")}</div>`;

  grafico("g-planes", {
    type: "bar",
    data: { labels: planes.map((p) => p.plan), datasets: [
      { label: "Vendidas", data: planes.map((p) => p.vendidas), backgroundColor: "#16181d", borderRadius: 4 },
      { label: "Activas hoy", data: planes.map((p) => p.activas), backgroundColor: "#a6d12a", borderRadius: 4 }] },
    options: { indexAxis: "y", scales: { y: { grid: { display: false } } } },
  });
  const colores = { efectivo: "#16181d", tarjeta: "#5c7a00", transferencia: "#a6d12a", nequi: "#d9dcd4" };
  grafico("g-metodos", {
    type: "bar",
    data: { labels: ingresos.map((x) => x.periodo), datasets: METODOS.map((m) => ({ label: cap(m), data: ingresos.map((x) => x[m]), backgroundColor: colores[m] })) },
    options: { scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: (v) => "$" + v / 1e6 + "M" } } },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${pesos(c.raw)}` } } } },
  });
  grafico("g-dias", {
    type: "bar",
    data: { labels: horas.por_dia.map((d) => d.dia), datasets: [{ data: horas.por_dia.map((d) => d.ingresos), backgroundColor: "#5c7a00", borderRadius: 4 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } } } },
  });
};

/* ============================ Navegación ============================ */
async function mostrar(nombre) {
  document.querySelectorAll("#menu a").forEach((a) => a.classList.toggle("active", a.dataset.view === nombre));
  $("#titulo").textContent = $(`#menu a[data-view="${nombre}"]`).textContent;
  $("#acciones").innerHTML = "";
  vista.onclick = null;
  vista.innerHTML = `<div class="vacio">Cargando…</div>`;
  $(".sidebar").classList.remove("abierta");
  location.hash = nombre;
  try { await vistas[nombre](); }
  catch (e) { vista.innerHTML = `<div class="panel vacio">No se pudo cargar: ${esc(e.message)}</div>`; }
}
$("#menu").addEventListener("click", (e) => { if (e.target.dataset.view) mostrar(e.target.dataset.view); });
$("#btn-menu").onclick = () => $(".sidebar").classList.toggle("abierta");

GET("/salud")
  .then(() => { $("#estado-bd").textContent = "MongoDB Atlas conectado"; $("#estado-bd").className = "estado-bd ok"; })
  .catch(() => { $("#estado-bd").textContent = "Sin conexión a la BD"; $("#estado-bd").className = "estado-bd error"; });

mostrar(vistas[location.hash.slice(1)] ? location.hash.slice(1) : "tablero");
