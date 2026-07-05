{% extends 'base.html' %}
{% block content %}
<header class="page-head"><div><h1>Check-List 5S</h1><p>Registra auditorías manteniendo la lógica original de cálculo por fase.</p></div></header>
<form class="card form" method="post" enctype="multipart/form-data">
  <div class="form-grid">
    <label>País<select name="pais" id="pais" required>{% for p in plantas|map(attribute='pais')|unique %}<option value="{{p}}">{{p}}</option>{% endfor %}</select></label>
    <label>Planta<select name="planta" id="planta" required></select></label>
    <label>Área<select name="area" id="area" required></select></label>
    <label>Auditor<input name="auditor" placeholder="Nombre del auditor" required></label>
    <label class="wide">Evidencia fotográfica<input type="file" name="evidencia" accept="image/*"></label>
  </div>
  <div class="questions">
  {% for fase, pregunta in preguntas %}
    {% if loop.first or preguntas[loop.index0-1][0] != fase %}<h3 class="phase" style="border-left-color: {{FASE_COLORS[fase]}}">{{fase}}</h3>{% endif %}
    <div class="question"><div><b>{{loop.index}}.</b> {{pregunta}}</div><div class="toggle"><label><input type="radio" name="q{{loop.index0}}" value="1" required> Sí</label><label><input type="radio" name="q{{loop.index0}}" value="0" required> No</label></div></div>
  {% endfor %}
  </div>
  <button class="btn blue submit">💾 Guardar auditoría</button>
</form>
<script id="plantas-json" type="application/json">{{ plantas|tojson }}</script>
{% endblock %}
