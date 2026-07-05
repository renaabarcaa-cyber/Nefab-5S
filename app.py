{% extends 'base.html' %}
{% block content %}
<header class="page-head"><div><h1>Dashboard</h1><p>Panel general de auditorías 5S, hallazgos y evidencia.</p></div><div class="actions"><a class="btn blue" href="{{ url_for('export_excel') }}">📥 Exportar Excel</a><a class="btn red" href="{{ url_for('export_pdf') }}">📄 Exportar PDF</a></div></header>
<section class="kpis">
  <div class="kpi"><span>📋 Auditorías realizadas</span><strong>{{total}}</strong></div>
  <div class="kpi"><span>📊 Promedio general</span><strong>{{avg}}%</strong></div>
  <div class="kpi"><span>🔍 Hallazgos abiertos</span><strong>{{abiertos}}</strong></div>
</section>
<section class="grid two">
  <div class="card"><h2>Promedio por fase 5S</h2>{% for f,p in fase_avg.items() %}<div class="bar-row"><span>{{f}}</span><div class="bar"><i style="width:{{p}}%"></i></div><b>{{p}}%</b></div>{% endfor %}</div>
  <div class="card"><h2>Resultados de auditorías</h2><canvas id="resultChart"></canvas></div>
</section>
<section class="grid two">
  <div class="card"><h2>Hallazgos por fase</h2><canvas id="phaseChart"></canvas></div>
  <div class="card"><h2>Estado de hallazgos</h2><canvas id="statusChart"></canvas></div>
</section>
{% if evidencias %}<section class="card"><h2>Evidencia fotográfica reciente</h2><div class="photos">{% for e in evidencias %}<div><img src="{{ url_for('static', filename='uploads/' ~ e.evidencia) }}"><small>{{ e.area or e.descripcion[:22] }}</small></div>{% endfor %}</div></section>{% endif %}
<section class="card"><h2>Últimas auditorías</h2><div class="table-wrap"><table><thead><tr><th>Fecha</th><th>País</th><th>Planta</th><th>Área</th><th>Auditor</th><th>% General</th><th>Estado</th></tr></thead><tbody>{% for a in auditorias|reverse %}<tr><td>{{a.fecha}}</td><td>{{a.pais}}</td><td>{{a.planta}}</td><td>{{a.area}}</td><td>{{a.auditor}}</td><td><b>{{a.pct_total}}%</b></td><td><span class="pill {{ estado_from_pct(a.pct_total)|lower }}">{{estado_from_pct(a.pct_total)}}</span></td></tr>{% else %}<tr><td colspan="7">Sin auditorías aún.</td></tr>{% endfor %}</tbody></table></div></section>
{% endblock %}
{% block scripts %}
<script>
makeDoughnut('resultChart', {{ result_counts|tojson }}, ['#8CC24A','#FDD835','#E53935']);
makeDoughnut('phaseChart', {{ findings_by_phase|tojson }}, ['#E53935','#FE8200','#F9A825','#8CC24A','#144E8C']);
makeDoughnut('statusChart', {{ status_counts|tojson }}, ['#FE8200','#FDD835','#8CC24A']);
</script>
{% endblock %}
