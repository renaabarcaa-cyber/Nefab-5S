{% extends 'base.html' %}
{% block content %}
<header class="page-head"><div><h1>Hallazgos y Tickets</h1><p>Registro, evidencia y cierre de hallazgos 5S.</p></div></header>
<section class="grid two">
<form class="card form" method="post" enctype="multipart/form-data"><h2>Registrar nuevo hallazgo</h2>
  <label>Fase 5S<select name="fase" id="faseHallazgo">{% for f in FASES %}<option>{{f}}</option>{% endfor %}</select></label>
  <label>Responsable<input name="responsable" required></label>
  <label>Fecha compromiso<input type="date" name="fecha_compromiso"></label>
  <label>Estado<select name="estado"><option>Abierto</option><option>En progreso</option><option>Cerrado</option></select></label>
  <label>Descripción<textarea name="descripcion" rows="4" placeholder="Describe el hallazgo"></textarea></label>
  <label>Catálogo<select name="catalogo_desc" id="catalogo"><option value="">Seleccionar posibilidad</option>{% for c in catalogo %}<option data-fase="{{c.fase}}" value="{{c.descripcion}}">{{c.descripcion}}</option>{% endfor %}</select></label>
  <label>Evidencia<input type="file" name="evidencia" accept="image/*"></label>
  <button class="btn blue submit">➕ Agregar hallazgo</button>
</form>
<div class="card"><h2>Catálogo de posibilidades</h2><ul class="catalog">{% for c in catalogo %}<li><b>{{c.fase}}</b><br>{{c.descripcion}}</li>{% endfor %}</ul></div>
</section>
<section class="card"><div class="card-head"><h2>Hallazgos registrados</h2><form><select name="estado" onchange="this.form.submit()"><option {% if estado=='Todos' %}selected{% endif %}>Todos</option><option {% if estado=='Abierto' %}selected{% endif %}>Abierto</option><option {% if estado=='En progreso' %}selected{% endif %}>En progreso</option><option {% if estado=='Cerrado' %}selected{% endif %}>Cerrado</option></select></form></div><div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Fase</th><th>Responsable</th><th>Descripción</th><th>Compromiso</th><th>Estado</th><th>Evidencia</th><th>Acción</th></tr></thead><tbody>{% for t in tickets|reverse %}<tr><td>{{t.fecha}}</td><td>{{t.fase}}</td><td>{{t.responsable}}</td><td>{{t.descripcion}}</td><td>{{t.fecha_compromiso}}</td><td><span class="pill">{{t.estado}}</span></td><td>{% if t.evidencia %}<a href="{{ url_for('static', filename='uploads/' ~ t.evidencia) }}" target="_blank">Ver foto</a>{% endif %}</td><td>{% if t.estado != 'Cerrado' %}<form method="post" action="{{ url_for('cerrar_hallazgo', ticket_id=t.id) }}"><button class="mini">Cerrar</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="8">Sin hallazgos.</td></tr>{% endfor %}</tbody></table></div></section>
{% endblock %}
