# -*- coding: utf-8 -*-
"""
Nefab 5S Web - v1.0
Flask + JSON local (o disco persistente via DATA_DIR) + Login con roles
Admin / Usuario. Mismo patron arquitectonico que VSM Manager Web:
un solo archivo, sin dependencias entre archivos propios, guardado
atomico con Lock, evidencia fotografica, listo para Render.

Modelo: Plantas -> Auditorias 5S (puntaje 1-5 por pilar) + Hallazgos
(con evidencia fotografica y seguimiento de accion correctiva).

Instalacion:
    pip install -r requirements.txt

Ejecutar:
    python app.py

Luego abrir en el navegador:
    http://127.0.0.1:5000
"""
from __future__ import annotations
import csv
import io
import json
import os
import time
import random
import string
import threading
import zipfile
import base64
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, abort, Response, send_from_directory,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader

# Colores Nefab
NB, NO, NG, NGR = "#144E8C", "#FE8200", "#8CC24A", "#88888D"
NBL, NGL, NOL = "#E6F1FB", "#EAF3DE", "#FFF3E0"
RED, REDL = "#E34948", "#FCEBEB"
WHITE, BG, CARD, BORDER, DARK, MUTED = "#FFFFFF", "#F4F6FB", "#FFFFFF", "#E2E8F0", "#1E293B", "#64748B"

AREAS = ["Logística", "Manufactura"]
AREA_COLOR = {"Logística": NB, "Manufactura": NO}

PILLARS = ["Seiri", "Seiton", "Seiso", "Seiketsu", "Shitsuke"]
PILLAR_LABELS = {
    "Seiri": "Seiri (Clasificar)", "Seiton": "Seiton (Ordenar)", "Seiso": "Seiso (Limpiar)",
    "Seiketsu": "Seiketsu (Estandarizar)", "Shitsuke": "Shitsuke (Disciplina)",
}
FASES = ["🔴 Seiri", "🟠 Seiton", "🟡 Seiso", "🟢 Seiketsu", "🔵 Shitsuke"]
FASE_KEYS = {"🔴 Seiri": "Seiri", "🟠 Seiton": "Seiton", "🟡 Seiso": "Seiso",
             "🟢 Seiketsu": "Seiketsu", "🔵 Shitsuke": "Shitsuke"}
FASE_COLOR = {"🔴 Seiri": "#E53935", "🟠 Seiton": "#FE8200", "🟡 Seiso": "#FDD835",
              "🟢 Seiketsu": "#8CC24A", "🔵 Shitsuke": "#144E8C"}

# Checklist fijo de la auditoria: 10 preguntas, 2 por cada fase (mismo orden
# y agrupacion que la app de escritorio: indices 0-1=Seiri, 2-3=Seiton, etc.)
PREGUNTAS = [
    ("🔴 Seiri", "¿Solo tiene lo que usa?"),
    ("🔴 Seiri", "¿Es de fácil acceso?"),
    ("🟠 Seiton", "¿Los elementos están identificados?"),
    ("🟠 Seiton", "¿Todo está en el lugar correcto?"),
    ("🟡 Seiso", "¿El lugar está limpio?"),
    ("🟡 Seiso", "¿Los depósitos de basura contienen el tipo correcto?"),
    ("🟢 Seiketsu", "¿Organización general según la norma?"),
    ("🟢 Seiketsu", "¿Se usan y actualizan los tableros de anuncios?"),
    ("🔵 Shitsuke", "¿Se mantiene capacitación frecuente de 5S?"),
    ("🔵 Shitsuke", "¿Las 5S se implementan y se siguen?"),
]
FASES_MAP_IDX = {"Seiri": [0, 1], "Seiton": [2, 3], "Seiso": [4, 5], "Seiketsu": [6, 7], "Shitsuke": [8, 9]}

DEFAULT_CATALOGO = [
    {"fase": "🔴 Seiri", "descripcion": "Herramientas o materiales innecesarios en el área"},
    {"fase": "🔴 Seiri", "descripcion": "Documentación antigua o desactualizada no eliminada"},
    {"fase": "🔴 Seiri", "descripcion": "Equipos obsoletos almacenados sin motivo"},
    {"fase": "🔴 Seiri", "descripcion": "Mezcla de materiales útiles con desechos"},
    {"fase": "🔴 Seiri", "descripcion": "Falta identificación de lo que se debe descartar"},
    {"fase": "🟠 Seiton", "descripcion": "Herramientas sin lugar definido o mal ubicadas"},
    {"fase": "🟠 Seiton", "descripcion": "Falta señalización en estanterías y cajones"},
    {"fase": "🟠 Seiton", "descripcion": "Mala organización de cables y utensilios"},
    {"fase": "🟠 Seiton", "descripcion": "Dificultad para acceder a elementos frecuentes"},
    {"fase": "🟠 Seiton", "descripcion": "Áreas de almacenamiento sobrecargadas"},
    {"fase": "🟡 Seiso", "descripcion": "Suciedad visible en maquinaria, pisos o superficies"},
    {"fase": "🟡 Seiso", "descripcion": "Fugas de aceite, grasa o residuos sin atender"},
    {"fase": "🟡 Seiso", "descripcion": "Equipos con polvo acumulado o manchas"},
    {"fase": "🟡 Seiso", "descripcion": "Áreas de difícil acceso sin limpieza regular"},
    {"fase": "🟡 Seiso", "descripcion": "Falta cronograma o responsables de limpieza"},
    {"fase": "🟢 Seiketsu", "descripcion": "Ausencia de procedimientos visuales o instructivos"},
    {"fase": "🟢 Seiketsu", "descripcion": "Falta consistencia entre turnos"},
    {"fase": "🟢 Seiketsu", "descripcion": "Etiquetado inconsistente o incompleto"},
    {"fase": "🟢 Seiketsu", "descripcion": "Señalética confusa o deteriorada"},
    {"fase": "🟢 Seiketsu", "descripcion": "No uso de formatos estandarizados"},
    {"fase": "🔵 Shitsuke", "descripcion": "No cumplimiento de normas básicas de orden"},
    {"fase": "🔵 Shitsuke", "descripcion": "Falta de compromiso del personal con las 5S"},
    {"fase": "🔵 Shitsuke", "descripcion": "No realización de auditorías internas periódicas"},
    {"fase": "🔵 Shitsuke", "descripcion": "Supervisores que no refuerzan la cultura 5S"},
    {"fase": "🔵 Shitsuke", "descripcion": "Inexistencia de capacitaciones o seguimientos"},
]

SCORE_OPTIONS = [1, 2, 3, 4, 5]
SEVERITIES = ["Alto", "Medio", "Bajo"]
FINDING_STATUSES = ["Abierto", "En progreso", "Cerrado"]

LANGUAGES = {"Español": "es", "English": "en", "Português": "pt"}
TRANSLATIONS = {
    "en": {
        "Plantas 5S": "5S Sites", "Plantas 5S Nefab": "Nefab 5S Sites", "Nueva planta": "New Site",
        "Nombre de la planta": "Site name", "Sitio / Operación": "Site / Operation",
        "Cliente": "Customer", "Responsable": "Owner", "Área": "Area", "Problema / Alcance": "Scope",
        "Cancelar": "Cancel", "Crear": "Create", "Guardar": "Save", "Abrir": "Open", "Eliminar": "Delete",
        "Total plantas": "Total sites", "Logística": "Logistics", "Manufactura": "Manufacturing",
        "Todos": "All", "Filtrar por área": "Filter by area", "Sin plantas en esta área.": "No sites in this area.",
        "Volver a plantas": "Back to sites", "Secciones de la planta": "Site sections",
        "Inicio": "Dashboard", "Auditorías": "Audits", "Hallazgos": "Findings", "Evidencias": "Evidence",
        "Exportar": "Export", "Salir": "Logout", "Planta activa": "Active site", "Actualizado": "Updated",
        "Guardado": "Saved", "Promedio general": "Overall average", "Auditorías realizadas": "Audits performed",
        "Hallazgos abiertos": "Open findings", "Hallazgos cerrados": "Closed findings",
        "Promedio por pilar": "Average by pillar", "Fecha": "Date",
        "Auditor": "Auditor", "Puntaje promedio": "Average score", "Observaciones": "Notes",
        "Registro de auditorías": "Audit log", "+ Nueva auditoría": "+ New audit",
        "Registro de hallazgos": "Findings log", "+ Nuevo hallazgo": "+ New finding",
        "Zona / Área": "Zone / Area", "Pilar": "Pillar", "Descripción": "Description",
        "Severidad": "Severity", "Acción correctiva": "Corrective action", "Fecha compromiso": "Due date",
        "Estado": "Status", "Alto": "High", "Medio": "Medium", "Bajo": "Low",
        "Abierto": "Open", "En progreso": "In progress", "Cerrado": "Closed",
        "Editar": "Edit", "Acciones": "Actions", "Buscar zona, descripción o acción": "Search zone, description or action",
        "Limpiar filtros": "Clear filters", "Editar seleccionado": "Edit selected",
        "Eliminar seleccionado": "Delete selected", "Agregar foto": "Add photo", "Subir evidencia": "Upload evidence",
        "Sin fotos registradas.": "No photos recorded.", "Comentario": "Comment", "Subir": "Upload",
        "Eliminar foto": "Delete photo", "Tomar o seleccionar foto": "Take or select photo",
        "¿Eliminar esta foto?": "Delete this photo?", "Registro fotográfico de evidencia": "Photo evidence log",
        "Exportar planta 5S": "Export 5S site", "Descargar ZIP (2 CSV)": "Download ZIP (2 CSV)",
        "Descargar reporte PDF": "Download PDF report", "Información de la planta": "Site information",
        "Idioma": "Language", "General": "General", "¿Eliminar esta planta 5S?": "Delete this 5S site?",
        "Campo requerido": "Required field",
        "opcional": "optional", "Evidencia fotográfica": "Photo evidence",
        "Puntaje por pilar": "Score by pillar", "Cerrar": "Close",
        "Del catálogo": "From catalog",
        "Resultados de auditorías": "Audit results", "Hallazgos por fase": "Findings by pillar",
        "Estado de hallazgos": "Findings status", "Evidencia fotográfica reciente": "Recent photo evidence",
        "Fase 5S": "5S Pillar", "filtrado por fase": "filtered by pillar", "Selecciona": "Select",
        "País": "Country", "Editar planta": "Edit site", "separadas por coma": "comma-separated",
        "Áreas / zonas de la planta": "Site areas / zones", "Catálogo de posibilidades": "Catalog of possibilities",
        "Gestionar catálogo": "Manage catalog", "Agregar al catálogo": "Add to catalog",
        "Volver": "Back", "Planta": "Site",
        "Cronograma de Seguimiento": "Follow-up Schedule", "Filtros": "Filters",
        "Fecha desde": "Date from", "Fecha hasta": "Date to", "Rango rápido": "Quick range",
        "Todo": "All", "Aplicar": "Apply", "Gantt semanal": "Weekly Gantt",
        "Área": "Area", "Hallazgo": "Finding", "Semana actual": "Current week",
        "Todas": "All", "Cronograma": "Schedule", "Fase": "Pillar", "Editar entrada": "Edit entry",
        "Catálogo de Países y Plantas": "Countries and Sites Catalog",
        "Registro maestro reutilizable al crear una planta o registrar una auditoría/hallazgo.":
            "Reusable master registry when creating a site or logging an audit/finding.",
        "Sin entradas.": "No entries.", "Agregar entrada": "Add entry", "Agregar": "Add", "Otro": "Other",
        "¿Solo tiene lo que usa?": "Do you only have what you use?",
        "¿Es de fácil acceso?": "Is it easily accessible?",
        "¿Los elementos están identificados?": "Are items identified?",
        "¿Todo está en el lugar correcto?": "Is everything in the right place?",
        "¿El lugar está limpio?": "Is the place clean?",
        "¿Los depósitos de basura contienen el tipo correcto?": "Do trash bins contain the correct type of waste?",
        "¿Organización general según la norma?": "Overall organization according to standard?",
        "¿Se usan y actualizan los tableros de anuncios?": "Are bulletin boards used and updated?",
        "¿Se mantiene capacitación frecuente de 5S?": "Is frequent 5S training maintained?",
        "¿Las 5S se implementan y se siguen?": "Are the 5S implemented and followed?",
    },
    "pt": {
        "Plantas 5S": "Plantas 5S",
        "Plantas 5S Nefab": "Plantas 5S Nefab",
        "Nueva planta": "Nova planta",
        "Nombre de la planta": "Nome da planta",
        "Sitio / Operación": "Local / Operação",
        "Cliente": "Cliente",
        "Responsable": "Responsável",
        "Área": "Área",
        "Problema / Alcance": "Problema / Escopo",
        "Cancelar": "Cancelar",
        "Crear": "Criar",
        "Guardar": "Salvar",
        "Abrir": "Abrir",
        "Eliminar": "Excluir",
        "Total plantas": "Total de plantas",
        "Logística": "Logística",
        "Manufactura": "Manufatura",
        "Todos": "Todos",
        "Filtrar por área": "Filtrar por área",
        "Sin plantas en esta área.": "Nenhuma planta nesta área.",
        "Volver a plantas": "Voltar às plantas",
        "Secciones de la planta": "Seções da planta",
        "Inicio": "Painel",
        "Auditorías": "Auditorias",
        "Hallazgos": "Achados",
        "Evidencias": "Evidências",
        "Exportar": "Exportar",
        "Salir": "Sair",
        "Planta activa": "Planta ativa",
        "Actualizado": "Atualizado",
        "Guardado": "Salvo",
        "Promedio general": "Média geral",
        "Auditorías realizadas": "Auditorias realizadas",
        "Hallazgos abiertos": "Achados abertos",
        "Hallazgos cerrados": "Achados fechados",
        "Promedio por pilar": "Média por pilar",
        "Fecha": "Data",
        "Auditor": "Auditor",
        "Puntaje promedio": "Pontuação média",
        "Observaciones": "Observações",
        "Registro de auditorías": "Registro de auditorias",
        "+ Nueva auditoría": "+ Nova auditoria",
        "Registro de hallazgos": "Registro de achados",
        "+ Nuevo hallazgo": "+ Novo achado",
        "Zona / Área": "Zona / Área",
        "Pilar": "Pilar",
        "Descripción": "Descrição",
        "Severidad": "Severidade",
        "Acción correctiva": "Ação corretiva",
        "Fecha compromiso": "Data limite",
        "Estado": "Status",
        "Alto": "Alto",
        "Medio": "Médio",
        "Bajo": "Baixo",
        "Abierto": "Aberto",
        "En progreso": "Em andamento",
        "Cerrado": "Fechado",
        "Editar": "Editar",
        "Acciones": "Ações",
        "Buscar zona, descripción o acción": "Buscar zona, descrição ou ação",
        "Limpiar filtros": "Limpar filtros",
        "Editar seleccionado": "Editar selecionado",
        "Eliminar seleccionado": "Excluir selecionado",
        "Agregar foto": "Adicionar foto",
        "Subir evidencia": "Enviar evidência",
        "Sin fotos registradas.": "Nenhuma foto registrada.",
        "Comentario": "Comentário",
        "Subir": "Enviar",
        "Eliminar foto": "Excluir foto",
        "Tomar o seleccionar foto": "Tirar ou selecionar foto",
        "¿Eliminar esta foto?": "Excluir esta foto?",
        "Registro fotográfico de evidencia": "Registro fotográfico de evidência",
        "Exportar planta 5S": "Exportar planta 5S",
        "Descargar ZIP (2 CSV)": "Baixar ZIP (2 CSV)",
        "Descargar reporte PDF": "Baixar relatório PDF",
        "Información de la planta": "Informações da planta",
        "Idioma": "Idioma",
        "General": "Geral",
        "¿Eliminar esta planta 5S?": "Excluir esta planta 5S?",
        "Campo requerido": "Campo obrigatório",
        "opcional": "opcional",
        "Evidencia fotográfica": "Evidência fotográfica",
        "Puntaje por pilar": "Pontuação por pilar",
        "Cerrar": "Fechar",
        "Del catálogo": "Do catálogo",
        "Resultados de auditorías": "Resultados das auditorias",
        "Hallazgos por fase": "Achados por pilar",
        "Estado de hallazgos": "Status dos achados",
        "Evidencia fotográfica reciente": "Evidência fotográfica recente",
        "Fase 5S": "Pilar 5S",
        "filtrado por fase": "filtrado por pilar",
        "Selecciona": "Selecione",
        "País": "País",
        "Editar planta": "Editar planta",
        "separadas por coma": "separadas por vírgula",
        "Áreas / zonas de la planta": "Áreas / zonas da planta",
        "Catálogo de posibilidades": "Catálogo de possibilidades",
        "Gestionar catálogo": "Gerenciar catálogo",
        "Agregar al catálogo": "Adicionar ao catálogo",
        "Volver": "Voltar",
        "Planta": "Planta",
        "Cronograma de Seguimiento": "Cronograma de acompanhamento",
        "Filtros": "Filtros",
        "Fecha desde": "Data de",
        "Fecha hasta": "Data até",
        "Rango rápido": "Intervalo rápido",
        "Todo": "Tudo",
        "Aplicar": "Aplicar",
        "Gantt semanal": "Gantt semanal",
        "Hallazgo": "Achado",
        "Semana actual": "Semana atual",
        "Todas": "Todas",
        "Cronograma": "Cronograma",
        "Fase": "Pilar", "Editar entrada": "Editar entrada",
        "Catálogo de Países y Plantas": "Catálogo de Países e Plantas",
        "Registro maestro reutilizable al crear una planta o registrar una auditoría/hallazgo.":
            "Registro mestre reutilizável ao criar uma planta ou registrar uma auditoria/achado.",
        "Sin entradas.": "Sem entradas.", "Agregar entrada": "Adicionar entrada", "Agregar": "Adicionar", "Otro": "Outro",
        "¿Solo tiene lo que usa?": "Você só tem o que usa?",
        "¿Es de fácil acceso?": "É de fácil acesso?",
        "¿Los elementos están identificados?": "Os itens estão identificados?",
        "¿Todo está en el lugar correcto?": "Tudo está no lugar correto?",
        "¿El lugar está limpio?": "O local está limpo?",
        "¿Los depósitos de basura contienen el tipo correcto?": "As lixeiras contêm o tipo correto de resíduo?",
        "¿Organización general según la norma?": "Organização geral de acordo com a norma?",
        "¿Se usan y actualizan los tableros de anuncios?": "Os quadros de avisos são usados e atualizados?",
        "¿Se mantiene capacitación frecuente de 5S?": "O treinamento frequente de 5S é mantido?",
        "¿Las 5S se implementan y se siguen?": "Os 5S são implementados e seguidos?",
    },
}


def tr(text):
    lang = session.get("lang", "es")
    if lang == "es":
        return text
    return TRANSLATIONS.get(lang, {}).get(text, text)

TEMPLATES = {
    'base.html': """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nefab 5S — Auditorías</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <img src="/logo.png" alt="Nefab" class="brand-logo">
    <span class="app-name">Nefab 5S<small>Auditorías y Hallazgos</small></span>
  </div>
  <div class="topbar-right">
    {% if current_user %}
    <span class="user-email">{{ current_user.email }}{% if current_user.role == "admin" %} <span class="role-badge">ADMIN</span>{% endif %}</span>
    {% endif %}
    <select class="lang-select" onchange="window.location.href=this.value">
      <option value="{{ url_for('set_lang', lang='es') }}" {{ 'selected' if session.get('lang','es')=='es' else '' }}>Español</option>
      <option value="{{ url_for('set_lang', lang='en') }}" {{ 'selected' if session.get('lang','es')=='en' else '' }}>English</option>
      <option value="{{ url_for('set_lang', lang='pt') }}" {{ 'selected' if session.get('lang','es')=='pt' else '' }}>Português</option>
    </select>
    {% if current_user %}
    <span class="avatar" title="{{ current_user.email }}">{{ current_user.initials }}</span>
    <a href="{{ url_for('logout') }}" class="lang-link">{{ tr("Salir") }}</a>
    {% endif %}
  </div>
</div>

<div class="layout">
  <nav class="sidebar">
    {% block sidebar %}{% endblock %}
  </nav>
  <main class="content">
    {% block content %}{% endblock %}
    <footer class="app-footer">© 2026 Nefab Group · Nefab 5S · Todos los derechos reservados</footer>
  </main>
</div>

</body>
</html>
""",
    'setup.html': """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nefab 5S — Configuración inicial</title>
<link rel="stylesheet" href="/style.css"></head>
<body>
<div class="auth-page">
  <div class="auth-card">
    <img src="/logo.png" alt="Nefab" class="brand-logo" style="margin-bottom:10px;">
    <h2>Configuración inicial</h2>
    <p class="muted">Aún no hay usuarios. Crea la cuenta de administrador.</p>
    {% if error %}<p class="error-note">{{ error }}</p>{% endif %}
    <form method="post">
      <label>Correo</label>
      <input type="email" name="email" required>
      <label>Contraseña</label>
      <input type="password" name="password" required minlength="6">
      <div class="form-actions">
        <button type="submit" class="btn-primary" style="width:100%;">Crear administrador</button>
      </div>
    </form>
  </div>
</div>
</body></html>
""",
    'login.html': """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nefab 5S — Iniciar sesión</title>
<link rel="stylesheet" href="/style.css"></head>
<body>
<div class="auth-page">
  <div class="auth-card">
    <img src="/logo.png" alt="Nefab" class="brand-logo" style="margin-bottom:10px;">
    <h2>Nefab 5S</h2>
    <p class="muted">Inicia sesión para continuar.</p>
    {% if error %}<p class="error-note">{{ error }}</p>{% endif %}
    <form method="post">
      <label>Correo</label>
      <input type="email" name="email" required autofocus>
      <label>Contraseña</label>
      <input type="password" name="password" required>
      <div class="form-actions">
        <button type="submit" class="btn-primary" style="width:100%;">Iniciar sesión</button>
      </div>
    </form>
  </div>
</div>
</body></html>
""",
    'admin_users.html': """{% extends "base.html" %}
{% block sidebar %}
  <a href="{{ url_for('plantas_list') }}" class="sidebar-btn">← {{ tr("Volver a plantas") }}</a>
  <div class="sidebar-label">Administración</div>
  <a href="{{ url_for('admin_users') }}" class="sidebar-btn active">👤 Usuarios</a>
{% endblock %}

{% block content %}
  <div class="table-toolbar">
    <h2>Usuarios</h2>
    <a href="{{ url_for('admin_user_new') }}" class="btn-primary">+ Nuevo usuario</a>
  </div>
  <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Correo</th><th>Rol</th><th>Acciones</th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>{{ u.email }}</td>
          <td><span class="pill {{ 'pill-red' if u.role=='admin' else 'pill-blue' }}">{{ 'Admin' if u.role=='admin' else 'Usuario' }}</span></td>
          <td class="actions-cell">
            {% if u.id != current.id %}
            <form method="post" action="{{ url_for('admin_user_delete', uid=u.id) }}" style="display:inline;" onsubmit="return confirm('¿Eliminar este usuario?');">
              <button type="submit" class="btn-mini btn-mini-danger">Eliminar</button>
            </form>
            {% else %}
            <span class="muted">(tú)</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
{% endblock %}
""",
    'cronograma.html': """{% extends "base.html" %}
{% block sidebar %}
  <a href="{{ url_for('plantas_list') }}" class="sidebar-btn">← {{ tr("Volver a plantas") }}</a>
{% endblock %}

{% block content %}
  <h2>{{ tr("Cronograma de Seguimiento") }}</h2>

  <div class="chart-card" style="margin-bottom:16px;">
    <h3>{{ tr("Filtros") }}</h3>
    <form method="get" id="cron-form">
      <div class="filters-bar" style="margin-bottom:10px;">
        <select name="pais">
          <option value="">{{ tr("País") }}: {{ tr("Todos") }}</option>
          {% for pa in paises %}<option value="{{ pa }}" {{ 'selected' if pais_f==pa }}>{{ pa }}</option>{% endfor %}
        </select>
        <select name="estado">
          <option value="">{{ tr("Estado") }}: {{ tr("Todos") }}</option>
          {% for s in FINDING_STATUSES %}<option value="{{ s }}" {{ 'selected' if estado_f==s }}>{{ tr(s) }}</option>{% endfor %}
        </select>
        <select name="fase">
          <option value="">{{ tr("Fase") }}: {{ tr("Todas") }}</option>
          {% for f in FASES %}<option value="{{ f }}" {{ 'selected' if fase_f==f }}>{{ f }}</option>{% endfor %}
        </select>
      </div>
      <div class="filters-bar">
        <span class="muted" style="font-size:12px;">{{ tr("Fecha desde") }}</span>
        <input type="date" name="date_from" id="cron-from" value="{{ date_from }}">
        <span class="muted" style="font-size:12px;">{{ tr("Fecha hasta") }}</span>
        <input type="date" name="date_to" id="cron-to" value="{{ date_to }}">
        <span class="muted" style="font-size:12px;">{{ tr("Rango rápido") }}</span>
        <button type="button" class="btn-icon-text" data-days="7">7d</button>
        <button type="button" class="btn-icon-text" data-days="30">30d</button>
        <button type="button" class="btn-icon-text" data-days="90">90d</button>
        <button type="button" class="btn-icon-text" data-days="0">{{ tr("Todo") }}</button>
        <button type="submit" class="btn-primary">▶ {{ tr("Aplicar") }}</button>
      </div>
    </form>
  </div>

  <div class="chart-card">
    <h3>{{ tr("Gantt semanal") }}</h3>
    <div class="table-wrap">
      <table class="data-table gantt-table">
        <thead>
          <tr>
            <th style="min-width:260px;">{{ tr("Área") }} / {{ tr("Hallazgo") }}</th>
            {% for w in weeks %}<th class="{{ 'gantt-current' if w.is_current else '' }}">{{ w.label }}</th>{% endfor %}
          </tr>
        </thead>
        <tbody>
          {% for r in rows %}
          <tr>
            <td class="gantt-row-label" style="border-left:5px solid {{ FASE_COLOR.get(r.pillar, NGR) }};">
              [{{ r.area }}] {{ r.description }}
              <div class="muted" style="font-size:10px;">{{ r.pais }} · {{ r.planta_name }}</div>
            </td>
            {% for w in weeks %}
            <td class="{{ 'gantt-current' if w.is_current else '' }}">
              {% if loop.index0 == r.week_idx %}
              <span class="gantt-h {{ 'gantt-h-cerrado' if r.status=='Cerrado' else 'gantt-h-abierto' }}">H</span>
              {% endif %}
            </td>
            {% endfor %}
          </tr>
          {% endfor %}
          {% if not rows %}
          <tr><td colspan="{{ weeks|length + 1 }}" class="muted-note">Sin hallazgos en el rango seleccionado.</td></tr>
          {% endif %}
        </tbody>
      </table>
    </div>
    <div class="gantt-legend">
      <span><span class="gantt-h gantt-h-abierto">H</span> {{ tr("Abierto") }}</span>
      <span><span class="gantt-h gantt-h-cerrado">H</span> {{ tr("Cerrado") }}</span>
      <span><span class="gantt-current-swatch"></span> {{ tr("Semana actual") }}</span>
    </div>
  </div>

<script>
document.querySelectorAll('#cron-form [data-days]').forEach(function(btn){
  btn.addEventListener('click', function(){
    var days = parseInt(btn.dataset.days, 10);
    var to = new Date();
    var toStr = to.toISOString().slice(0,10);
    document.getElementById('cron-to').value = toStr;
    if (days === 0) {
      document.getElementById('cron-from').value = '2020-01-01';
    } else {
      var from = new Date();
      from.setDate(from.getDate() - days);
      document.getElementById('cron-from').value = from.toISOString().slice(0,10);
    }
    document.getElementById('cron-form').submit();
  });
});
</script>
{% endblock %}
""",
    'paises_plantas.html': """{% extends "base.html" %}
{% block sidebar %}
  <a href="{{ url_for('plantas_list') }}" class="sidebar-btn">← {{ tr("Volver a plantas") }}</a>
{% endblock %}

{% block content %}
  <h2>{{ tr("Catálogo de Países y Plantas") }}</h2>
  <p class="muted-note">{{ tr("Registro maestro reutilizable al crear una planta o registrar una auditoría/hallazgo.") }}</p>

  <div class="form-card" style="margin-bottom:20px;">
    <h3 style="margin-top:0;">{{ tr("Editar entrada") if edit_item else tr("Agregar entrada") }}</h3>
    <form method="post" action="{{ url_for('paises_plantas_add') }}">
      <input type="hidden" name="pid" value="{{ pid }}">
      {% if edit_idx is not none %}<input type="hidden" name="idx" value="{{ edit_idx }}">{% endif %}
      <div class="form-row-3">
        <div>
          <label>{{ tr("País") }}</label>
          <input type="text" name="pais" value="{{ edit_item.pais if edit_item else '' }}" required>
        </div>
        <div>
          <label>{{ tr("Planta") }}</label>
          <input type="text" name="planta" value="{{ edit_item.planta if edit_item else '' }}" required>
        </div>
        <div>
          <label>{{ tr("Áreas / zonas de la planta") }} ({{ tr("separadas por coma") }})</label>
          <input type="text" name="areas" value="{{ edit_item.areas|join(', ') if edit_item else '' }}" placeholder="Ej: Inbound, Packing, Outbound">
        </div>
      </div>
      <div class="form-actions">
        {% if edit_item %}
        <a href="{{ url_for('paises_plantas_view', pid=pid) }}" class="btn-secondary">{{ tr("Cancelar") }}</a>
        {% endif %}
        <button type="submit" class="btn-primary">{{ tr("Guardar") if edit_item else tr("Agregar") }}</button>
      </div>
    </form>
  </div>

  <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>{{ tr("País") }}</th><th>{{ tr("Planta") }}</th><th>{{ tr("Áreas / zonas de la planta") }}</th><th>{{ tr("Acciones") }}</th></tr></thead>
      <tbody>
        {% for idx, r in registro %}
        <tr>
          <td>{{ r.pais }}</td>
          <td>{{ r.planta }}</td>
          <td>{{ r.areas|join(', ') }}</td>
          <td class="actions-cell">
            <a href="{{ url_for('paises_plantas_view', pid=pid, edit_idx=idx) }}" class="btn-mini">{{ tr("Editar") }}</a>
            <form method="post" action="{{ url_for('paises_plantas_delete', idx=idx, pid=pid) }}" style="display:inline;" onsubmit="return confirm('¿Eliminar esta entrada?');">
              <button type="submit" class="btn-mini btn-mini-danger">{{ tr("Eliminar") }}</button>
            </form>
          </td>
        </tr>
        {% endfor %}
        {% if not registro %}
        <tr><td colspan="4" class="muted-note">{{ tr("Sin entradas.") }}</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>
{% endblock %}
""",
    'catalogo.html': """{% extends "base.html" %}
{% block sidebar %}
  {% if pid %}
  <a href="{{ url_for('planta_hallazgos', pid=pid) }}" class="sidebar-btn">← {{ tr("Volver") }}</a>
  {% else %}
  <a href="{{ url_for('plantas_list') }}" class="sidebar-btn">← {{ tr("Volver a plantas") }}</a>
  {% endif %}
{% endblock %}

{% block content %}
  <h2>{{ tr("Catálogo de posibilidades") }}</h2>
  <p class="muted-note">Catálogo global de descripciones sugeridas para hallazgos, compartido entre todas las plantas.</p>

  <div class="form-card" style="margin-bottom:20px;">
    <h3 style="margin-top:0;">{{ tr("Editar entrada") if edit_item else tr("Agregar al catálogo") }}</h3>
    <form method="post" action="{{ url_for('catalogo_add') }}">
      <input type="hidden" name="pid" value="{{ pid }}">
      {% if edit_idx is not none %}<input type="hidden" name="idx" value="{{ edit_idx }}">{% endif %}
      <div class="form-row-2">
        <div>
          <label>{{ tr("Fase") }}</label>
          <select name="fase">
            {% for f in FASES %}<option value="{{ f }}" {{ 'selected' if edit_item and edit_item.fase==f }}>{{ f }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <label>{{ tr("Descripción") }}</label>
          <input type="text" name="descripcion" value="{{ edit_item.descripcion if edit_item else '' }}" required>
        </div>
      </div>
      <div class="form-actions">
        {% if edit_item %}
        <a href="{{ url_for('catalogo_view', pid=pid) }}" class="btn-secondary">{{ tr("Cancelar") }}</a>
        {% endif %}
        <button type="submit" class="btn-primary">{{ tr("Guardar") if edit_item else tr("Agregar al catálogo") }}</button>
      </div>
    </form>
  </div>

  {% for f in FASES %}
  <div class="chart-card" style="margin-bottom:14px;">
    <h3 style="color:{{ FASE_COLOR.get(f, NB) }};">{{ f }}</h3>
    {% if grouped.get(f) %}
    <table class="data-table">
      <tbody>
        {% for real_idx, c in grouped[f] %}
        <tr>
          <td>{{ c.descripcion }}</td>
          <td class="actions-cell" style="width:150px;">
            <a href="{{ url_for('catalogo_view', pid=pid, edit_idx=real_idx) }}" class="btn-mini">{{ tr("Editar") }}</a>
            <form method="post" action="{{ url_for('catalogo_delete', idx=real_idx, pid=pid) }}" style="display:inline;" onsubmit="return confirm('¿Eliminar esta entrada del catálogo?');">
              <button type="submit" class="btn-mini btn-mini-danger">{{ tr("Eliminar") }}</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="muted-note">Sin entradas.</p>
    {% endif %}
  </div>
  {% endfor %}
{% endblock %}
""",
    'admin_user_form.html': """{% extends "base.html" %}
{% block sidebar %}
  <a href="{{ url_for('admin_users') }}" class="sidebar-btn">← Volver a usuarios</a>
{% endblock %}

{% block content %}
  <div class="form-card">
    <h2>Nuevo usuario</h2>
    {% if error %}<p class="error-note">{{ error }}</p>{% endif %}
    <form method="post">
      <label>Correo</label>
      <input type="email" name="email" required>
      <label>Contraseña</label>
      <input type="password" name="password" required minlength="6">
      <label>Rol</label>
      <select name="role">
        <option value="user">Usuario</option>
        <option value="admin">Administrador</option>
      </select>
      <div class="form-actions">
        <a href="{{ url_for('admin_users') }}" class="btn-secondary">Cancelar</a>
        <button type="submit" class="btn-primary">Crear usuario</button>
      </div>
    </form>
  </div>
{% endblock %}
""",
    '_sidebar_planta.html': """<a href="{{ url_for('plantas_list') }}" class="sidebar-btn">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="M11 18l-6-6 6-6"/></svg>
{{ tr("Volver a plantas") }}</a>
<div class="sidebar-label">{{ p.get('name','') }}</div>
<div class="sidebar-label">{{ tr("Secciones de la planta") }}</div>
<a href="{{ url_for('planta_overview', pid=p.id) }}" class="sidebar-btn {{ 'active' if active=='Inicio' else '' }}">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l3-4"/><circle cx="12" cy="15" r="1"/></svg>
{{ tr("Inicio") }}</a>
<a href="{{ url_for('planta_auditorias', pid=p.id) }}" class="sidebar-btn {{ 'active' if active=='Auditorías' else '' }}">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
{{ tr("Auditorías") }}</a>
<a href="{{ url_for('planta_hallazgos', pid=p.id) }}" class="sidebar-btn {{ 'active' if active=='Hallazgos' else '' }}">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/></svg>
{{ tr("Hallazgos") }}</a>
<a href="{{ url_for('cronograma_view') }}" class="sidebar-btn">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="17" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/></svg>
{{ tr("Cronograma") }}</a>
<a href="{{ url_for('planta_evidencia', pid=p.id) }}" class="sidebar-btn {{ 'active' if active=='Evidencias' else '' }}">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-2h6l2 2h3v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8z"/><circle cx="12" cy="13" r="3.5"/></svg>
{{ tr("Evidencias") }}</a>
<a href="{{ url_for('planta_export', pid=p.id) }}" class="sidebar-btn {{ 'active' if active=='Exportar' else '' }}">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="M8 11l4 4 4-4"/><path d="M4 19h16"/></svg>
{{ tr("Exportar") }}</a>
{% if current_user and current_user.role == "admin" %}
<div class="sidebar-label">Administración</div>
<a href="{{ url_for('admin_users') }}" class="sidebar-btn">
<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h0a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v0a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>
Usuarios</a>
{% endif %}
<div class="active-project-panel">
  <div class="active-project-label">{{ tr("Planta activa") }}</div>
  <div class="active-project-name">{{ p.get('name','') }}</div>
  <div class="active-project-updated">{{ tr("Actualizado") }}: {{ p.get('updated_at', p.get('created_at','—')) }}</div>
  <div class="active-project-status">🟢 {{ tr("Guardado") }}</div>
</div>
""",
    'plantas_list.html': """{% extends "base.html" %}
{% block sidebar %}
  <div class="sidebar-label">{{ tr("Plantas 5S Nefab") }}</div>
  <a href="{{ url_for('new_planta_view') }}" class="sidebar-btn primary">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
  {{ tr("Nueva planta") }}</a>
  <div class="sidebar-label">{{ tr("Filtrar por área") }}</div>
  <a href="{{ url_for('plantas_list', area='Todos') }}" class="sidebar-btn {{ 'active' if area_filter=='Todos' else '' }}">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
  {{ tr("Todos") }}</a>
  {% for a in AREAS %}
  <a href="{{ url_for('plantas_list', area=a) }}" class="sidebar-btn {{ 'active' if area_filter==a else '' }}">
    {% if a=='Logística' %}
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 16V7a1 1 0 0 1 1-1h9v10"/><path d="M13 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/></svg>
    {% else %}
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20V10l6 4v-4l6 4V6l6 4v10z"/></svg>
    {% endif %}
    {{ tr(a) }}
  </a>
  {% endfor %}
  <div class="sidebar-label">General</div>
  <a href="{{ url_for('cronograma_view') }}" class="sidebar-btn">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="17" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/></svg>
  {{ tr("Cronograma") }}</a>
  <a href="{{ url_for('catalogo_view') }}" class="sidebar-btn">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h13a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2z"/></svg>
  {{ tr("Catálogo de posibilidades") }}</a>
  <a href="{{ url_for('paises_plantas_view') }}" class="sidebar-btn">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12c0-5 4-9 10-9s10 4 10 9-4 9-10 9-10-4-10-9z"/><path d="M2 12h20"/><path d="M12 3c2.5 2.5 4 6 4 9s-1.5 6.5-4 9c-2.5-2.5-4-6-4-9s1.5-6.5 4-9z"/></svg>
  {{ tr("Catálogo de Países y Plantas") }}</a>
  {% if current_user and current_user.role == "admin" %}
  <div class="sidebar-label">Administración</div>
  <a href="{{ url_for('admin_users') }}" class="sidebar-btn">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h0a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v0a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>
  Usuarios</a>
  {% endif %}
{% endblock %}

{% block content %}
  <h1 class="page-title">{{ tr("Plantas 5S") }}</h1>

  <div class="kpi-row">
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NB }}">{{ total }}</div><div class="kpi-label">{{ tr("Total plantas") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NG }}">{{ n_log }}</div><div class="kpi-label">{{ tr("Logística") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NO }}">{{ n_man }}</div><div class="kpi-label">{{ tr("Manufactura") }}</div></div>
  </div>

  {% if not plantas %}
    <p class="muted-note">{{ tr("Sin plantas en esta área.") }}</p>
  {% endif %}

  <div class="project-grid">
    {% for p in plantas %}
    <div class="project-card">
      <div class="area-badge" style="background:{{ AREA_COLOR.get(p.get('area','Logística'), NB) }}">{{ tr(p.get('area','Logística')) }}</div>
      <h3>{{ p.get('name','') }}</h3>
      <p class="muted">{{ p.get('pais','') }}{% if p.get('pais') %} · {% endif %}{{ p.get('customer','') }} · {{ p.get('site','') }} · {{ p.get('created_at','') }}</p>
      <p class="muted">{{ p._num_auditorias }} auditorías · {{ tr("Promedio general") }}: {{ p._promedio }}/5</p>
      <div class="card-actions">
        <a href="{{ url_for('planta_overview', pid=p.id) }}" class="btn-primary">{{ tr("Abrir") }}</a>
        <a href="{{ url_for('edit_planta_view', pid=p.id) }}" class="btn-secondary">{{ tr("Editar") }}</a>
        <form method="post" action="{{ url_for('delete_planta', pid=p.id) }}" onsubmit="return confirm('{{ tr('¿Eliminar esta planta 5S?') }}');" style="display:inline;">
          <button type="submit" class="btn-danger">{{ tr("Eliminar") }}</button>
        </form>
      </div>
    </div>
    {% endfor %}
  </div>
{% endblock %}
""",
    'planta_form.html': """{% extends "base.html" %}
{% block sidebar %}
  <a href="{{ url_for('plantas_list') }}" class="sidebar-btn">← {{ tr("Volver a plantas") }}</a>
{% endblock %}

{% block content %}
  <div class="form-card">
    <h2>{{ tr("Editar planta") if old else tr("Nueva planta") }}</h2>
    <form method="post">
      <div class="form-row-2">
        <div>
          <label>{{ tr("País") }}</label>
          <select id="pp-pais">
            <option value="">{{ tr("Selecciona") }}...</option>
            {% for pa in registro|map(attribute='pais')|unique|sort %}<option value="{{ pa }}">{{ pa }}</option>{% endfor %}
            <option value="__otro__">+ {{ tr("Otro") }}</option>
          </select>
          <input type="text" name="pais" id="pp-pais-text" value="{{ old.get('pais','') }}" placeholder="Ej: Chile, Brasil, México" style="margin-top:6px;">
        </div>
        <div>
          <label>{{ tr("Planta") }} ({{ tr("Del catálogo") }})</label>
          <select id="pp-planta">
            <option value="">{{ tr("Selecciona") }}...</option>
          </select>
          <p class="muted-note" style="margin:4px 0 0;">
            <a href="{{ url_for('paises_plantas_view') }}" target="_blank">{{ tr("Gestionar catálogo") }}</a>
          </p>
        </div>
      </div>

      <label>{{ tr("Nombre de la planta") }}</label>
      <input type="text" name="name" id="pp-name" value="{{ old.get('name','') }}" required>

      <label>{{ tr("Sitio / Operación") }}</label>
      <input type="text" name="site" value="{{ old.get('site','') }}">

      <label>{{ tr("Cliente") }}</label>
      <input type="text" name="customer" value="{{ old.get('customer','') }}">

      <label>{{ tr("Responsable") }}</label>
      <input type="text" name="owner" value="{{ old.get('owner','') }}">

      <label>{{ tr("Área") }}</label>
      <select name="area">
        {% for a in AREAS %}
        <option value="{{ a }}" {{ 'selected' if old.get('area')==a }}>{{ tr(a) }}</option>
        {% endfor %}
      </select>

      <label>{{ tr("Áreas / zonas de la planta") }} ({{ tr("separadas por coma") }})</label>
      <input type="text" name="areas" id="pp-areas" value="{{ old.get('areas',[])|join(', ') }}" placeholder="Ej: Inbound, Packing, Woodshop, Outbound, Quality">

      <label>{{ tr("Problema / Alcance") }}</label>
      <textarea name="problem" rows="3">{{ old.get('problem','') }}</textarea>

      <div class="form-actions">
        <a href="{{ url_for('plantas_list') }}" class="btn-secondary">{{ tr("Cancelar") }}</a>
        <button type="submit" class="btn-primary">{{ tr("Guardar") if old else tr("Crear") }}</button>
      </div>
    </form>
  </div>

<script>
(function(){
  var REGISTRO = {{ registro|tojson }};
  var paisSel = document.getElementById('pp-pais');
  var paisText = document.getElementById('pp-pais-text');
  var plantaSel = document.getElementById('pp-planta');
  var nameInput = document.getElementById('pp-name');
  var areasInput = document.getElementById('pp-areas');

  function refreshPlantaOptions(){
    var pais = paisSel.value === '__otro__' ? '' : paisSel.value;
    plantaSel.innerHTML = '<option value="">Selecciona...</option>';
    REGISTRO.filter(function(r){ return r.pais === pais; }).forEach(function(r){
      var opt = document.createElement('option');
      opt.value = r.planta;
      opt.textContent = r.planta;
      opt.dataset.areas = (r.areas || []).join(', ');
      plantaSel.appendChild(opt);
    });
  }
  paisSel.addEventListener('change', function(){
    if (paisSel.value === '__otro__') {
      paisText.style.display = '';
      paisText.value = '';
      paisText.focus();
    } else if (paisSel.value) {
      paisText.style.display = 'none';
      paisText.value = paisSel.value;
    }
    refreshPlantaOptions();
  });
  plantaSel.addEventListener('change', function(){
    var opt = plantaSel.options[plantaSel.selectedIndex];
    if (!opt || !opt.value) return;
    if (!nameInput.value) nameInput.value = opt.value;
    if (opt.dataset.areas) areasInput.value = opt.dataset.areas;
  });

  // Al cargar: si ya hay un pais guardado (modo edicion), preseleccionar el select si existe en el catalogo.
  var currentPais = paisText.value;
  if (currentPais) {
    var found = Array.prototype.slice.call(paisSel.options).some(function(o){ return o.value === currentPais; });
    paisSel.value = found ? currentPais : '__otro__';
    paisText.style.display = found ? 'none' : '';
  } else {
    paisText.style.display = 'none';
  }
  refreshPlantaOptions();
})();
</script>
{% endblock %}
""",
    'planta_overview.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="project-header">
    <span class="area-badge" style="background:{{ AREA_COLOR.get(p.get('area','Logística'), NB) }}">{{ tr(p.get('area','Logística')) }}</span>
    <span class="project-name">{{ p.get('name','') }}</span>
    <span class="muted">{{ p.get('customer','') }} · {{ p.get('site','') }}</span>
  </div>

  <div class="kpi-row kpi-row-5">
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NB }}">{{ stats.promedio }}%</div><div class="kpi-label">{{ tr("Promedio general") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NGR }}">{{ stats.num_auditorias }}</div><div class="kpi-label">{{ tr("Auditorías realizadas") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ RED }}">{{ stats.abiertos }}</div><div class="kpi-label">{{ tr("Hallazgos abiertos") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NG }}">{{ stats.cerrados }}</div><div class="kpi-label">{{ tr("Hallazgos cerrados") }}</div></div>
    <div class="kpi-card"><div class="kpi-value" style="color:{{ NO }}">{{ stats.total_hallazgos }}</div><div class="kpi-label">{{ tr("Hallazgos") }}</div></div>
  </div>

  <div class="three-col">
    <div class="chart-card">
      <h3>{{ tr("Resultados de auditorías") }}</h3>
      {% for clas, count in stats.resultado_counts.items() %}
      <div class="progress-row">
        <span class="progress-label">{{ CLASIFICACION_LABEL.get(clas, clas) }}</span>
        <div class="progress-track"><div class="progress-fill" style="width:{{ (count/stats.num_auditorias*100) if stats.num_auditorias else 0 }}%;background:{{ CLASIFICACION_COLOR.get(clas, NGR) }};"></div></div>
        <span class="progress-value">{{ count }}</span>
      </div>
      {% endfor %}
    </div>
    <div class="chart-card">
      <h3>{{ tr("Hallazgos por fase") }}</h3>
      {% for f, count in stats.fase_counts.items() %}
      <div class="progress-row">
        <span class="progress-label">{{ f }}</span>
        <div class="progress-track"><div class="progress-fill" style="width:{{ (count/stats.total_hallazgos*100) if stats.total_hallazgos else 0 }}%;background:{{ FASE_COLOR.get(f, NGR) }};"></div></div>
        <span class="progress-value">{{ count }}</span>
      </div>
      {% endfor %}
    </div>
    <div class="chart-card">
      <h3>{{ tr("Estado de hallazgos") }}</h3>
      {% for est, count in stats.estado_counts.items() %}
      <div class="progress-row">
        <span class="progress-label">{{ tr(est) }}</span>
        <div class="progress-track"><div class="progress-fill" style="width:{{ (count/stats.total_hallazgos*100) if stats.total_hallazgos else 0 }}%;background:{{ NG if est=='Cerrado' else (RED if est=='Abierto' else NO) }};"></div></div>
        <span class="progress-value">{{ count }}</span>
      </div>
      {% endfor %}
    </div>
  </div>

  <div class="two-col">
    <div class="chart-card">
      <h3>{{ tr("Promedio por pilar") }} (última auditoría)</h3>
      {% for pil in PILLARS %}
      <div class="progress-row">
        <span class="progress-label">{{ PILLAR_LABELS.get(pil, pil) }}</span>
        <div class="progress-track"><div class="progress-fill" style="width:{{ stats.pilares.get(pil,0) }}%;background:{{ NG if stats.pilares.get(pil,0) >= 80 else (NO if stats.pilares.get(pil,0) >= 60 else RED) }};"></div></div>
        <span class="progress-value">{{ stats.pilares.get(pil,0) }}%</span>
      </div>
      {% endfor %}
    </div>

    <div class="chart-card">
      <h3>{{ tr("Información de la planta") }}</h3>
      <table class="info-table">
        <tr><td class="muted">{{ tr("País") }}</td><td>{{ p.get('pais','—') }}</td></tr>
        <tr><td class="muted">{{ tr("Sitio / Operación") }}</td><td>{{ p.get('site','—') }}</td></tr>
        <tr><td class="muted">{{ tr("Cliente") }}</td><td>{{ p.get('customer','—') }}</td></tr>
        <tr><td class="muted">{{ tr("Responsable") }}</td><td>{{ p.get('owner','—') }}</td></tr>
        <tr><td class="muted">{{ tr("Área") }}</td><td>{{ tr(p.get('area','Logística')) }}</td></tr>
        <tr><td class="muted">{{ tr("Áreas / zonas de la planta") }}</td><td>{{ p.get('areas',[])|join(', ') or '—' }}</td></tr>
        <tr><td class="muted">{{ tr("Problema / Alcance") }}</td><td>{{ p.get('problem','—') }}</td></tr>
      </table>
    </div>
    <div class="chart-card" style="margin-top:12px;">
      <a href="{{ url_for('edit_planta_view', pid=p.id) }}" class="btn-secondary" style="display:inline-block;">✏️ {{ tr("Editar planta") }}</a>
    </div>
  </div>

  {% if p.get('evidence') %}
  <div class="chart-card" style="margin-top:16px;">
    <h3>{{ tr("Evidencia fotográfica reciente") }}</h3>
    <div class="evidence-grid">
      {% for ev in p.get('evidence',[])[-4:]|reverse %}
      <div class="evidence-card">
        <a href="{{ url_for('evidencia_photo', pid=p.id, filename=ev.filename) }}" target="_blank">
          <img src="{{ url_for('evidencia_photo', pid=p.id, filename=ev.filename) }}" class="evidence-thumb">
        </a>
        <div class="evidence-caption">{{ ev.get('caption','') or '—' }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}
{% endblock %}
""",
    'planta_auditorias.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="table-toolbar">
    <h2>{{ tr("Registro de auditorías") }}</h2>
    <a href="{{ url_for('auditoria_form', pid=p.id) }}" class="btn-primary">{{ tr("+ Nueva auditoría") }}</a>
  </div>

  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th>{{ tr("Fecha") }}</th><th>{{ tr("Zona / Área") }}</th><th>{{ tr("Auditor") }}</th>
          {% for f in FASES %}<th>{{ f }}</th>{% endfor %}
          <th>% General</th><th>{{ tr("Estado") }}</th><th>{{ tr("Observaciones") }}</th><th>{{ tr("Acciones") }}</th>
        </tr>
      </thead>
      <tbody>
        {% for a in p.get('auditorias',[]) %}
        {% set clas = a.get('clasificacion') or clasificacion_pct(audit_avg(a)) %}
        <tr>
          <td>{{ a.get('fecha','') }}</td>
          <td>{{ a.get('area','') or '-' }}</td>
          <td>{{ a.get('auditor','') }}</td>
          {% for f in FASES %}<td>{{ a.get('pct_' ~ FASE_KEYS.get(f, f), 0) }}%</td>{% endfor %}
          <td><strong>{{ audit_avg(a) }}%</strong></td>
          <td><span class="pill" style="background:{{ CLASIFICACION_COLOR.get(clas,NGR) }};color:#fff;">{{ CLASIFICACION_LABEL.get(clas, clas) }}</span></td>
          <td class="muted">{{ a.get('notes','') or '-' }}</td>
          <td class="actions-cell">
            {% if a.get('evidencia') %}
            <a href="{{ url_for('evidencia_photo', pid=p.id, filename=a.get('evidencia')) }}" target="_blank" class="btn-mini">📷</a>
            {% endif %}
            <a href="{{ url_for('auditoria_form', pid=p.id, idx=loop.index0) }}" class="btn-mini">{{ tr("Editar") }}</a>
            <form method="post" action="{{ url_for('auditoria_delete', pid=p.id, idx=loop.index0) }}" style="display:inline;" onsubmit="return confirm('¿Eliminar?');">
              <button type="submit" class="btn-mini btn-mini-danger">{{ tr("Eliminar") }}</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
{% endblock %}
""",
    'auditoria_form.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="form-card form-card-wide">
    <h2>{{ tr("Nueva auditoría") }}</h2>
    <form method="post" enctype="multipart/form-data">
      <div class="form-row-3">
        <div>
          <label>{{ tr("Fecha") }}</label>
          <input type="date" name="date" value="{{ old.get('fecha','') }}" required>
        </div>
        <div>
          <label>{{ tr("Zona / Área") }}</label>
          {% if p.get('areas') %}
          <select name="area">
            <option value="">—</option>
            {% for ar in p.get('areas',[]) %}<option value="{{ ar }}" {{ 'selected' if old.get('area')==ar }}>{{ ar }}</option>{% endfor %}
          </select>
          {% else %}
          <input type="text" name="area" value="{{ old.get('area','') }}" placeholder="Ej: Inbound, Packing, Woodshop">
          {% endif %}
        </div>
        <div>
          <label>{{ tr("Auditor") }}</label>
          <input type="text" name="auditor" value="{{ old.get('auditor','') }}">
        </div>
      </div>

      <div class="form-section-label">Check-List 5S</div>
      {% set old_resp = old.get('respuestas', []) %}
      {% for fase, pregunta in PREGUNTAS %}
      {% set checked_val = old_resp[loop.index0] if loop.index0 < old_resp|length else none %}
      <div class="checklist-row">
        <span class="checklist-fase" style="color:{{ FASE_COLOR.get(fase, NB) }};">{{ fase }}</span>
        <span class="checklist-question">{{ tr(pregunta) }}</span>
        <div class="checklist-btns">
          <label class="chk-btn chk-si"><input type="radio" name="q{{ loop.index0 }}" value="1" {{ 'checked' if checked_val == 1 else '' }}> ✓ Sí</label>
          <label class="chk-btn chk-no"><input type="radio" name="q{{ loop.index0 }}" value="0" {{ 'checked' if checked_val == 0 else '' }}> ✗ No</label>
        </div>
      </div>
      {% endfor %}

      <div class="form-section-label">{{ tr("Evidencia fotográfica") }} ({{ tr("opcional") }})</div>
      <input type="file" name="photo" accept="image/*" capture="environment">

      <label style="margin-top:16px;">{{ tr("Observaciones") }}</label>
      <textarea name="notes" rows="3">{{ old.get('notes','') }}</textarea>

      <div class="form-actions">
        <a href="{{ url_for('planta_auditorias', pid=p.id) }}" class="btn-secondary">{{ tr("Cancelar") }}</a>
        <button type="submit" class="btn-primary">{{ tr("Guardar") }}</button>
      </div>
    </form>
  </div>

<script>
(function(){
  // Refuerza visualmente la seleccion Si/No con JS (no depender solo de :has() en CSS,
  // que puede fallar en algunos navegadores/WebViews).
  document.querySelectorAll('.checklist-row').forEach(function(row){
    var labels = row.querySelectorAll('.chk-btn');
    function refresh(){
      labels.forEach(function(lbl){
        var input = lbl.querySelector('input');
        lbl.classList.toggle('chk-selected', input.checked);
      });
    }
    labels.forEach(function(lbl){
      lbl.querySelector('input').addEventListener('change', refresh);
    });
    refresh();
  });
})();
</script>
{% endblock %}
""",
    'planta_hallazgos.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="table-toolbar">
    <h2>{{ tr("Registro de hallazgos") }}</h2>
    <a href="{{ url_for('hallazgo_form', pid=p.id) }}" class="btn-primary">{{ tr("+ Nuevo hallazgo") }}</a>
  </div>

  <div class="filters-bar">
    <input type="text" id="hz-search" placeholder="{{ tr('Buscar zona, descripción o acción') }}...">
    <select id="filter-pillar">
      <option value="">{{ tr("Pilar") }}: {{ tr("Todos") }}</option>
      {% for f in FASES %}<option value="{{ f }}">{{ f }}</option>{% endfor %}
    </select>
    <select id="filter-severity">
      <option value="">{{ tr("Severidad") }}: {{ tr("Todos") }}</option>
      {% for s in SEVERITIES %}<option value="{{ s }}">{{ tr(s) }}</option>{% endfor %}
    </select>
    <select id="filter-status">
      <option value="">{{ tr("Estado") }}: {{ tr("Todos") }}</option>
      {% for s in FINDING_STATUSES %}<option value="{{ s }}">{{ tr(s) }}</option>{% endfor %}
    </select>
    <button type="button" id="btn-clear-filters" class="btn-secondary">🔄 {{ tr("Limpiar filtros") }}</button>
  </div>

  <div class="table-wrap">
    <table class="data-table" id="hallazgos-table">
      <thead>
        <tr>
          <th><input type="checkbox" id="select-all"></th>
          <th>#</th><th>{{ tr("Fecha") }}</th><th>{{ tr("País") }}</th><th>{{ tr("Planta") }}</th><th>{{ tr("Zona / Área") }}</th><th>{{ tr("Pilar") }}</th>
          <th>{{ tr("Descripción") }}</th><th>{{ tr("Severidad") }}</th><th>{{ tr("Acción correctiva") }}</th>
          <th>{{ tr("Responsable") }}</th><th>{{ tr("Fecha compromiso") }}</th><th>{{ tr("Estado") }}</th>
          <th>{{ tr("Acciones") }}</th>
        </tr>
      </thead>
      <tbody>
        {% for h in p.get('hallazgos',[]) %}
        <tr data-idx="{{ loop.index0 }}"
            data-search="{{ (h.get('area','') ~ ' ' ~ h.get('description','') ~ ' ' ~ h.get('corrective_action',''))|lower }}"
            data-pillar="{{ h.get('pillar','') }}" data-severity="{{ h.get('severity','') }}" data-status="{{ h.get('status','') }}">
          <td><input type="checkbox" class="row-select" value="{{ loop.index0 }}"></td>
          <td class="muted">{{ loop.index }}</td>
          <td>{{ h.get('date','') }}</td>
          <td>{{ p.get('pais','—') }}</td>
          <td>{{ p.get('name','') }}</td>
          <td>{{ h.get('area','') }}</td>
          <td>{{ h.get('pillar','') }}</td>
          <td>{{ h.get('description','') }}</td>
          <td><span class="pill {{ 'pill-red' if h.get('severity')=='Alto' else ('pill-orange' if h.get('severity')=='Medio' else 'pill-green') }}">{{ tr(h.get('severity','')) }}</span></td>
          <td>{{ h.get('corrective_action','') or '-' }}</td>
          <td>{{ h.get('responsible','') }}</td>
          <td>{{ h.get('due_date','') or '-' }}</td>
          <td><span class="pill {{ 'pill-green' if h.get('status')=='Cerrado' else ('pill-red' if h.get('status')=='Abierto' else 'pill-blue') }}">{{ tr(h.get('status','')) }}</span></td>
          <td class="actions-cell">
            {% if h.get('evidencia') %}
            <a href="{{ url_for('evidencia_photo', pid=p.id, filename=h.get('evidencia')) }}" target="_blank" class="btn-mini">📷</a>
            {% endif %}
            <a href="{{ url_for('hallazgo_form', pid=p.id, idx=loop.index0) }}" class="btn-mini">{{ tr("Editar") }}</a>
            {% if h.get('status') != 'Cerrado' %}
            <form method="post" action="{{ url_for('hallazgo_close', pid=p.id, idx=loop.index0) }}" style="display:inline;">
              <button type="submit" class="btn-mini" style="background:{{ NG }};">✔ {{ tr("Cerrar") }}</button>
            </form>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p class="muted-note" id="row-count-note"></p>

  <form method="post" id="bulk-delete-form" action="{{ url_for('hallazgos_bulk_delete', pid=p.id) }}"></form>
  <div class="bulk-actions-bar">
    <button type="button" id="btn-edit-selected" class="btn-primary" disabled>✏️ {{ tr("Editar seleccionado") }}</button>
    <button type="button" id="btn-delete-selected" class="btn-danger" disabled>🗑️ {{ tr("Eliminar seleccionado") }}</button>
  </div>

<script>
(function(){
  var pid = "{{ p.id }}";
  var rows = Array.prototype.slice.call(document.querySelectorAll('#hallazgos-table tbody tr'));
  var searchInput = document.getElementById('hz-search');
  var fPillar = document.getElementById('filter-pillar');
  var fSeverity = document.getElementById('filter-severity');
  var fStatus = document.getElementById('filter-status');
  var rowCountNote = document.getElementById('row-count-note');

  function applyFilters(){
    var q = (searchInput.value || '').toLowerCase();
    var pil = fPillar.value, sev = fSeverity.value, st = fStatus.value;
    var visible = 0;
    rows.forEach(function(row){
      var show = (!q || row.dataset.search.indexOf(q) > -1)
        && (!pil || row.dataset.pillar === pil)
        && (!sev || row.dataset.severity === sev)
        && (!st || row.dataset.status === st);
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    rowCountNote.textContent = 'Mostrando ' + visible + ' de ' + rows.length;
  }
  [searchInput, fPillar, fSeverity, fStatus].forEach(function(el){
    el.addEventListener('input', applyFilters);
    el.addEventListener('change', applyFilters);
  });
  document.getElementById('btn-clear-filters').addEventListener('click', function(){
    searchInput.value=''; fPillar.value=''; fSeverity.value=''; fStatus.value='';
    applyFilters();
  });
  applyFilters();

  var selectAll = document.getElementById('select-all');
  var btnEdit = document.getElementById('btn-edit-selected');
  var btnDelete = document.getElementById('btn-delete-selected');
  function getSelected(){
    return Array.prototype.slice.call(document.querySelectorAll('.row-select:checked'))
      .filter(function(cb){ return cb.closest('tr').style.display !== 'none'; })
      .map(function(cb){ return cb.value; });
  }
  function refreshBulkButtons(){
    var sel = getSelected();
    btnEdit.disabled = sel.length !== 1;
    btnDelete.disabled = sel.length === 0;
  }
  document.querySelectorAll('.row-select').forEach(function(cb){ cb.addEventListener('change', refreshBulkButtons); });
  selectAll.addEventListener('change', function(){
    rows.forEach(function(row){ if (row.style.display !== 'none') row.querySelector('.row-select').checked = selectAll.checked; });
    refreshBulkButtons();
  });
  btnEdit.addEventListener('click', function(){
    var sel = getSelected();
    if (sel.length === 1) window.location.href = '/planta/' + pid + '/hallazgos/save?idx=' + sel[0];
  });
  btnDelete.addEventListener('click', function(){
    var sel = getSelected();
    if (!sel.length) return;
    if (!confirm('¿Eliminar ' + sel.length + ' hallazgo(s) seleccionado(s)?')) return;
    var form = document.getElementById('bulk-delete-form');
    form.innerHTML = '';
    sel.forEach(function(idx){
      var inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = 'idx'; inp.value = idx;
      form.appendChild(inp);
    });
    form.submit();
  });
  refreshBulkButtons();
})();
</script>
{% endblock %}
""",
    'hallazgo_form.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="form-card form-card-wide">
    <h2>{{ tr("Hallazgo 5S") }}</h2>
    {% if error %}<p class="error-note">{{ tr("Campo requerido") }}</p>{% endif %}
    <form method="post" enctype="multipart/form-data">
      <div class="form-row-3">
        <div>
          <label>{{ tr("Fecha") }}</label>
          <input type="date" name="date" value="{{ old.get('date','') }}">
        </div>
        <div>
          <label>{{ tr("Zona / Área") }}</label>
          {% if p.get('areas') %}
          <select name="area" required>
            <option value="">—</option>
            {% for ar in p.get('areas',[]) %}<option value="{{ ar }}" {{ 'selected' if old.get('area')==ar }}>{{ ar }}</option>{% endfor %}
          </select>
          {% else %}
          <input type="text" name="area" value="{{ old.get('area','') }}" required>
          {% endif %}
        </div>
        <div>
          <label>{{ tr("Fase 5S") }}</label>
          <div class="fase-btns" id="hz-fase-btns">
            {% for f in FASES %}
            <label class="fase-btn" style="--fase-color:{{ FASE_COLOR.get(f, NB) }};">
              <input type="radio" name="pillar" value="{{ f }}" {{ 'checked' if old.get('pillar')==f or (not old.get('pillar') and loop.first) else '' }}>
              {{ FASE_KEYS.get(f, f) }}
            </label>
            {% endfor %}
          </div>
        </div>
      </div>

      <label>{{ tr("Del catálogo") }} ({{ tr("filtrado por fase") }}) — <a href="{{ url_for('catalogo_view', pid=p.id) }}" style="font-weight:400;font-size:11px;">{{ tr("Gestionar catálogo") }}</a></label>
      <select id="hz-catalogo">
        <option value="">{{ tr("Selecciona") }}...</option>
      </select>

      <label>{{ tr("Descripción") }}</label>
      <textarea name="description" id="hz-desc" rows="2">{{ old.get('description','') }}</textarea>

      <div class="form-row-2">
        <div>
          <label>{{ tr("Severidad") }}</label>
          <select name="severity">
            {% for s in SEVERITIES %}<option value="{{ s }}" {{ 'selected' if old.get('severity')==s }}>{{ tr(s) }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <label>{{ tr("Estado") }}</label>
          <select name="status">
            {% for s in FINDING_STATUSES %}<option value="{{ s }}" {{ 'selected' if old.get('status')==s }}>{{ tr(s) }}</option>{% endfor %}
          </select>
        </div>
      </div>

      <label>{{ tr("Acción correctiva") }}</label>
      <textarea name="corrective_action" rows="2">{{ old.get('corrective_action','') }}</textarea>

      <div class="form-row-2">
        <div>
          <label>{{ tr("Responsable") }}</label>
          <input type="text" name="responsible" value="{{ old.get('responsible','') }}">
        </div>
        <div>
          <label>{{ tr("Fecha compromiso") }}</label>
          <input type="date" name="due_date" value="{{ old.get('due_date','') }}">
        </div>
      </div>

      <label>{{ tr("Evidencia fotográfica") }} ({{ tr("opcional") }})</label>
      <input type="file" name="photo" accept="image/*" capture="environment">

      <div class="form-actions">
        <a href="{{ url_for('planta_hallazgos', pid=p.id) }}" class="btn-secondary">{{ tr("Cancelar") }}</a>
        <button type="submit" class="btn-primary">{{ tr("Guardar") }}</button>
      </div>
    </form>
  </div>

<script>
(function(){
  var CATALOGO = {{ catalogo|tojson }};
  var faseBtnsContainer = document.getElementById('hz-fase-btns');
  var faseRadios = faseBtnsContainer.querySelectorAll('input[type=radio]');
  var catSel = document.getElementById('hz-catalogo');
  var descTa = document.getElementById('hz-desc');

  function getSelectedFase(){
    var checked = faseBtnsContainer.querySelector('input:checked');
    return checked ? checked.value : '';
  }
  function refreshFaseButtons(){
    faseRadios.forEach(function(r){
      r.closest('.fase-btn').classList.toggle('fase-selected', r.checked);
    });
  }
  function refreshCatalogo(){
    var fase = getSelectedFase();
    catSel.innerHTML = '<option value="">Selecciona...</option>';
    CATALOGO.filter(function(c){ return c.fase === fase; }).forEach(function(c){
      var opt = document.createElement('option');
      opt.value = c.descripcion;
      opt.textContent = c.descripcion;
      catSel.appendChild(opt);
    });
  }
  faseRadios.forEach(function(r){
    r.addEventListener('change', function(){ refreshFaseButtons(); refreshCatalogo(); });
  });
  catSel.addEventListener('change', function(){
    if (catSel.value) descTa.value = catSel.value;
  });
  refreshFaseButtons();
  refreshCatalogo();
})();
</script>
{% endblock %}
""",
    'planta_evidencia.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <h2>{{ tr("Registro fotográfico de evidencia") }}</h2>

  <div class="form-card" style="margin-bottom:20px;">
    <form method="post" action="{{ url_for('evidencia_upload', pid=p.id) }}" enctype="multipart/form-data">
      <label>{{ tr("Tomar o seleccionar foto") }}</label>
      <input type="file" name="photo" accept="image/*" capture="environment" required>
      <label>{{ tr("Comentario") }}</label>
      <input type="text" name="caption" placeholder="Ej: Zona de Picking, pasillo B">
      <div class="form-actions">
        <button type="submit" class="btn-primary">📷 {{ tr("Subir") }}</button>
      </div>
    </form>
  </div>

  {% if not p.get('evidence', []) %}
    <p class="muted-note">{{ tr("Sin fotos registradas.") }}</p>
  {% endif %}

  <div class="evidence-grid">
    {% for ev in p.get('evidence', [])|reverse %}
    <div class="evidence-card">
      <a href="{{ url_for('evidencia_photo', pid=p.id, filename=ev.filename) }}" target="_blank">
        <img src="{{ url_for('evidencia_photo', pid=p.id, filename=ev.filename) }}" class="evidence-thumb">
      </a>
      <div class="evidence-caption">{{ ev.get('caption','') or '—' }}</div>
      <div class="evidence-date">{{ ev.get('date','') }}</div>
      <form method="post" action="{{ url_for('evidencia_delete', pid=p.id, filename=ev.filename) }}" onsubmit="return confirm('{{ tr('¿Eliminar esta foto?') }}');">
        <button type="submit" class="btn-mini btn-mini-danger">{{ tr("Eliminar foto") }}</button>
      </form>
    </div>
    {% endfor %}
  </div>
{% endblock %}
""",
    'planta_export.html': """{% extends "base.html" %}
{% block sidebar %}{% include "_sidebar_planta.html" %}{% endblock %}

{% block content %}
  <div class="form-card">
    <h2>{{ tr("Exportar planta 5S") }}</h2>
    <p class="muted">Exporta auditorías y hallazgos a CSV.</p>
    <a href="{{ url_for('planta_export_zip', pid=p.id) }}" class="btn-primary" style="display:inline-block;margin-top:12px;">
      📦 {{ tr("Descargar ZIP (2 CSV)") }}
    </a>
    <p class="muted" style="margin-top:18px;">Reporte PDF con información, KPIs, auditorías, hallazgos y evidencia fotográfica.</p>
    <a href="{{ url_for('planta_report_pdf', pid=p.id) }}" class="btn-primary" style="display:inline-block;margin-top:4px;background:{{ RED }};">
      📄 {{ tr("Descargar reporte PDF") }}
    </a>
  </div>
{% endblock %}
""",
}


NEFAB_LOGO_B64 = (
    "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"
    "d6lNaz9zPWIAAAAASUVORK5CYII="
)

STYLE_CSS = """:root{
  --blue:#144E8C; --dark:#0D3A6E; --orange:#FE8200; --green:#8CC24A;
  --gray:#88888D; --red:#E34948; --bg:#F4F6FB; --card:#FFFFFF;
  --border:#E2E8F0; --text:#1E293B; --muted:#64748B;
}
*{box-sizing:border-box;}
body{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);}
a{text-decoration:none;color:inherit;}

.topbar{
  height:56px;background:var(--dark);border-bottom:none;
  display:flex;align-items:center;justify-content:space-between;padding:0 16px;
  position:sticky;top:0;z-index:10;
}
.topbar-left{display:flex;align-items:center;gap:12px;overflow:hidden;}
.brand{font-weight:700;color:#fff;font-size:15px;white-space:nowrap;line-height:1.1;}
.brand-logo{height:26px;width:auto;display:block;filter:brightness(0) invert(1);}
.brand small{display:block;font-size:7px;color:rgba(255,255,255,0.65);font-weight:400;letter-spacing:1px;}
.app-name{font-weight:600;font-size:14px;color:#fff;border-left:1px solid rgba(255,255,255,0.25);padding-left:10px;white-space:nowrap;}
.app-name small{display:block;font-size:11px;color:rgba(255,255,255,0.65);font-weight:400;}
.topbar-right{display:flex;align-items:center;gap:10px;flex-shrink:0;}
.lang-select{background:rgba(255,255,255,0.12);color:#fff;border:1px solid rgba(255,255,255,0.3);
  border-radius:6px;padding:5px 8px;font-size:12px;font-weight:600;}
.lang-select option{color:#000;}
.avatar{width:30px;height:30px;border-radius:50%;background:var(--orange);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;}
.user-email{font-size:12px;color:rgba(255,255,255,0.85);white-space:nowrap;}
.role-badge{background:var(--orange);color:#fff;font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;}
.topbar .lang-link{color:rgba(255,255,255,0.75);}
.topbar .lang-link.active{background:rgba(255,255,255,0.2);color:#fff;}

.auth-page{min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:var(--bg);padding:20px;}
.auth-card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:28px;max-width:380px;width:100%;}
.auth-card h2{margin:4px 0 4px;font-size:19px;}
.auth-card label{display:block;font-size:12px;color:var(--muted);margin:14px 0 4px;font-weight:600;}
.auth-card input{width:100%;border:1px solid var(--border);border-radius:7px;padding:10px 12px;
  font-size:14px;font-family:inherit;}

.layout{display:flex;min-height:calc(100vh - 56px);}
.sidebar{width:230px;background:#fff;border-right:1px solid var(--border);padding:14px 0;
  flex-shrink:0;display:flex;flex-direction:column;}
.active-project-panel{margin-top:auto;padding:14px 16px;border-top:1px solid var(--border);
  background:#F8FAFC;}
.active-project-label{font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;
  margin-bottom:4px;}
.active-project-name{font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px;}
.active-project-updated{font-size:11px;color:var(--muted);margin-bottom:5px;}
.active-project-status{font-size:11px;color:var(--green);font-weight:600;}
.sidebar-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;
  padding:14px 18px 6px;}
.sidebar-btn{display:flex;align-items:center;gap:11px;padding:11px 18px;margin:2px 10px;
  font-size:13.5px;color:var(--text);border-radius:9px;font-weight:500;}
.sidebar-btn svg{flex-shrink:0;color:var(--muted);}
.sidebar-btn:hover{background:#F0F4F9;}
.sidebar-btn.active{background:var(--dark);color:#fff;font-weight:700;}
.sidebar-btn.active svg{color:#fff;}
.sidebar-btn.primary{background:var(--orange);color:#fff;margin:4px 12px;border-radius:8px;
  text-align:center;font-weight:700;justify-content:center;}
.sidebar-btn.primary:hover{background:#d96e00;}
.sidebar-btn.primary svg{color:#fff;}

.content{flex:1;padding:20px;min-width:0;overflow-x:hidden;display:flex;flex-direction:column;min-height:calc(100vh - 56px);}
.app-footer{margin-top:auto;padding-top:24px;text-align:center;font-size:11px;color:var(--muted);}

.page-title{margin:0 0 16px;font-size:20px;font-weight:700;}
.muted{color:var(--muted);font-size:12px;}
.muted-note{color:var(--muted);font-size:12px;margin:6px 0 14px;}
.error-note{color:var(--red);font-size:12px;font-weight:600;}

.kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;}
.kpi-row-5{grid-template-columns:repeat(auto-fit,minmax(110px,1fr));}
.kpi-row-6{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:12px;text-align:center;}
.kpi-value{font-size:22px;font-weight:700;}
.kpi-label{font-size:11px;color:var(--muted);margin-top:2px;}
.kpi-icon-card{display:flex;align-items:center;gap:10px;text-align:left;padding:14px;}
.kpi-icon-circle{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:16px;flex-shrink:0;}
.kpi-icon-body{min-width:0;}
.kpi-icon-body .kpi-value{font-size:19px;}
.kpi-icon-body .kpi-label{font-size:11px;font-weight:600;color:var(--text);margin:1px 0;}
.kpi-sublabel{font-size:10px;color:var(--muted);}

.page-tabs{display:flex;gap:4px;border-bottom:2px solid var(--border);margin-bottom:16px;flex-wrap:wrap;}
.page-tab{background:none;border:none;padding:10px 16px;font-size:13px;font-weight:600;
  color:var(--muted);cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;}
.page-tab.active{color:var(--blue);border-bottom-color:var(--blue);}
.tab-panel{display:none;}
.tab-panel.active{display:block;}

.filters-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center;}
.filters-bar input[type=text]{flex:1;min-width:200px;border:1px solid var(--border);border-radius:7px;
  padding:8px 12px;font-size:13px;font-family:inherit;}
.filters-bar select{border:1px solid var(--border);border-radius:7px;padding:8px 10px;
  font-size:12px;font-family:inherit;background:#fff;}

.bulk-actions-bar{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap;}
.bulk-actions-bar button:disabled{opacity:0.45;cursor:not-allowed;}

.project-grid{display:grid;grid-template-columns:1fr;gap:12px;}
.project-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;}
.project-card h3{margin:6px 0 2px;font-size:15px;}
.area-badge{display:inline-block;color:#fff;font-size:10px;font-weight:700;
  padding:3px 9px;border-radius:6px;}
.card-actions{display:flex;gap:8px;margin-top:10px;}

.btn-primary{background:var(--blue);color:#fff;border:none;border-radius:7px;
  padding:9px 16px;font-size:13px;font-weight:700;cursor:pointer;display:inline-block;}
.btn-primary:hover{background:var(--dark);}
.btn-secondary{background:#fff;color:var(--muted);border:1px solid var(--border);border-radius:7px;
  padding:9px 16px;font-size:13px;cursor:pointer;display:inline-block;}
.btn-danger{background:#fff;color:var(--red);border:1px solid var(--red);border-radius:7px;
  padding:9px 14px;font-size:13px;cursor:pointer;}
.btn-mini{font-size:11px;padding:5px 9px;border-radius:5px;background:var(--blue);color:#fff;
  border:none;cursor:pointer;display:inline-block;}
.btn-mini-danger{background:var(--red);}

.table-toolbar{display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:8px;margin-bottom:6px;}
.table-toolbar h2{margin:0;font-size:17px;}

.table-wrap{overflow-x:auto;background:var(--card);border:1px solid var(--border);
  border-radius:10px;}
.data-table{width:100%;border-collapse:collapse;font-size:12px;min-width:640px;}
.data-table th{background:var(--blue);color:#fff;text-align:left;padding:8px 10px;
  font-size:11px;white-space:nowrap;}
.data-table td{padding:8px 10px;border-bottom:1px solid var(--border);}
.actions-cell{white-space:nowrap;}
.actions-cell .btn-mini{margin-right:4px;}

.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;}
.pill-blue{background:#E6F1FB;color:var(--blue);}
.pill-orange{background:#FFF3E0;color:#b5610a;}
.pill-green{background:#EAF3DE;color:#4c7a17;}
.pill-red{background:#FCEBEB;color:var(--red);}

.form-card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px;max-width:560px;}
.form-card h2{margin:0 0 14px;font-size:17px;}
.form-card label{display:block;font-size:12px;color:var(--muted);margin:12px 0 4px;font-weight:600;}
.form-card input, .form-card select, .form-card textarea{
  width:100%;border:1px solid var(--border);border-radius:7px;padding:9px 10px;font-size:13px;
  font-family:inherit;background:#fff;color:var(--text);
}
.form-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}
.form-row-2{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.form-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}
.form-actions{display:flex;gap:10px;margin-top:20px;}
.form-card-wide{max-width:760px;}
.form-section-label{font-size:11px;font-weight:700;color:var(--blue);text-transform:uppercase;
  letter-spacing:0.4px;margin:22px 0 4px;padding-top:14px;border-top:1px solid var(--border);}
.form-section-label:first-of-type{border-top:none;padding-top:0;margin-top:6px;}

.checklist-row{display:flex;align-items:center;gap:10px;padding:8px 0;
  border-bottom:1px solid var(--border);flex-wrap:wrap;}
.checklist-fase{font-size:11px;font-weight:700;width:90px;flex-shrink:0;}
.checklist-question{flex:1;font-size:13px;min-width:160px;}
.checklist-btns{display:flex;gap:6px;flex-shrink:0;}
.chk-btn{display:flex;align-items:center;gap:4px;font-size:12px;font-weight:700;
  padding:6px 10px;border-radius:6px;cursor:pointer;border:1px solid var(--border);}
.chk-btn input{margin:0;width:auto;}
.chk-si{color:var(--green);}
.chk-si:has(input:checked), .chk-si.chk-selected{background:var(--green);color:#fff;border-color:var(--green);}
.chk-no{color:var(--red);}
.chk-no:has(input:checked), .chk-no.chk-selected{background:var(--red);color:#fff;border-color:var(--red);}

.fase-btns{display:flex;gap:6px;flex-wrap:wrap;}
.fase-btn{display:flex;align-items:center;gap:0;font-size:12px;font-weight:700;
  padding:8px 12px;border-radius:6px;cursor:pointer;border:2px solid var(--fase-color);
  color:var(--fase-color);background:#fff;}
.fase-btn input{position:absolute;opacity:0;width:0;height:0;}
.fase-btn:has(input:checked), .fase-btn.fase-selected{background:var(--fase-color);color:#fff;}

.gantt-table{min-width:100%;}
.gantt-table th{text-align:center;min-width:44px;}
.gantt-table td{text-align:center;padding:6px 4px;}
.gantt-row-label{text-align:left !important;font-size:12px;padding-left:10px !important;white-space:normal;}
.gantt-current{background:#EAF1FA;}
.gantt-h{display:inline-block;width:22px;height:22px;line-height:22px;border-radius:5px;
  font-size:11px;font-weight:700;color:#fff;}
.gantt-h-abierto{background:var(--red);}
.gantt-h-cerrado{background:var(--green);}
.gantt-legend{display:flex;gap:18px;margin-top:12px;font-size:12px;color:var(--muted);align-items:center;}
.gantt-legend span{display:flex;align-items:center;gap:6px;}
.gantt-current-swatch{display:inline-block;width:14px;height:14px;border-radius:3px;background:#EAF1FA;
  border:1px solid var(--blue);}
.btn-icon-text{border:1px solid var(--border);background:#fff;border-radius:6px;padding:6px 12px;
  font-size:12px;cursor:pointer;color:var(--text);}

.two-col{display:grid;grid-template-columns:1fr;gap:14px;}
.three-col{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:16px;}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;}
.chart-card h3{margin:0 0 12px;font-size:13px;color:var(--blue);text-transform:uppercase;font-weight:700;}

.progress-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px;}
.progress-label{width:110px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.progress-track{flex:1;height:10px;background:var(--border);border-radius:6px;overflow:hidden;}
.progress-fill{height:100%;border-radius:6px;}
.progress-value{width:34px;text-align:right;font-weight:700;flex-shrink:0;}

.info-table{width:100%;font-size:13px;border-collapse:collapse;}
.info-table td{padding:6px 4px;vertical-align:top;border-bottom:1px solid var(--border);}
.info-table td:first-child{width:40%;}

.project-header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.project-name{font-weight:700;font-size:16px;color:var(--blue);}

.vsm-map-scroll{display:flex;overflow-x:auto;gap:0;padding:8px 0;align-items:center;}
.vsm-proc-box{background:#F0F5FB;border:2px solid var(--blue);border-radius:8px;
  padding:10px 14px;min-width:150px;flex-shrink:0;font-size:12px;}
.vsm-proc-box strong{color:var(--blue);font-size:13px;}
.vsm-proc-line{font-size:11.5px;color:var(--text);margin-top:3px;font-weight:600;}
.vsm-arrow{padding:0 8px;color:var(--muted);font-size:16px;flex-shrink:0;}
.vsm-arrow-group{color:var(--orange);font-weight:700;font-size:20px;}

.timeline-bar{flex:1;border-radius:6px;padding:8px 14px;font-size:13px;font-weight:700;border:1px solid;}
.timeline-bar-va{background:#EAF3DE;border-color:var(--green);color:#3b6d11;}
.timeline-bar-nva{background:#FCEBEB;border-color:var(--red);color:var(--red);}
.timeline-bar-ct{background:#E6F1FB;border-color:var(--blue);color:var(--blue);}
.timeline-bar-wt{background:#FFF3E0;border-color:var(--orange);color:#b5610a;}

.evidence-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px;}
.evidence-card{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:8px;text-align:center;}
.evidence-thumb{width:100%;height:120px;object-fit:cover;border-radius:6px;display:block;}
.evidence-caption{font-size:12px;margin-top:6px;color:var(--text);word-break:break-word;}
.evidence-date{font-size:10px;color:var(--muted);margin-bottom:6px;}

/* ── Mobile: sidebar se convierte en barra horizontal scrollable ── */
@media (max-width: 760px){
  .layout{flex-direction:column;}
  .sidebar{
    width:100%;display:flex;flex-direction:row;overflow-x:auto;white-space:nowrap;
    padding:8px 6px;border-right:none;border-bottom:1px solid var(--border);
    -webkit-overflow-scrolling:touch;
  }
  .sidebar-label{display:none;}
  .active-project-panel{display:none;}
  .sidebar-btn{flex-shrink:0;padding:8px 14px;border-radius:20px;margin-right:6px;
    border:1px solid var(--border);}
  .sidebar-btn.active{border-color:transparent;}
  .sidebar-btn.primary{margin:0 6px 0 0;}
  .content{padding:14px;}
  .kpi-row{grid-template-columns:repeat(2,1fr);}
  .form-row, .form-row-2, .form-row-3{grid-template-columns:1fr;}
  .two-col{grid-template-columns:1fr;}
  .app-name{display:none;}
}
"""


# ── Rutas de datos ─────────────────────────────────────────────────────────
def _resolve_data_dir():
    """Intenta usar una carpeta 'data' junto al script; si no es escribible
    (puede pasar en algunos entornos de Android), usa una carpeta en el
    home del usuario como respaldo, para que la app nunca falle por esto.
    Si existe la variable de entorno DATA_DIR (por ejemplo, apuntando a un
    disco persistente en Render), esa tiene prioridad sobre todo lo demas."""
    candidates = []
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates += [Path(__file__).resolve().parent / "data", Path.home() / "Nefab_5S_Web_data"]
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return c
        except Exception:
            continue
    # Ultimo recurso: carpeta temporal del sistema
    fallback = Path(tempfile.gettempdir()) / "Nefab_5S_Web_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = _resolve_data_dir()
PLANTAS_FILE = DATA_DIR / "plantas_5s.json"
DB_FILE = DATA_DIR / "nefab5s.db"
PHOTOS_DIR = DATA_DIR / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_PHOTO_EXT = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}

# ── Persistencia SQLite ──────────────────────────────────────────────────
# Reemplaza el JSON de archivo unico para plantas/auditorias/hallazgos/
# evidencia: cada guardado ahora es una fila individual (INSERT/UPDATE/
# DELETE), evitando que dos personas guardando casi al mismo tiempo en la
# misma planta se pisen los cambios entre si.
import sqlite3

_HALLAZGO_COLS = ["date", "area", "pillar", "description", "severity", "status",
                  "corrective_action", "responsible", "due_date", "evidencia"]
_AUDIT_FLAT_COLS = (["fecha", "area", "auditor", "notes", "pct_total", "clasificacion", "evidencia"]
                     + [f"pct_{pil}" for pil in PILLARS])


def get_db():
    conn = sqlite3.connect(str(DB_FILE), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    audit_pct_cols = ",".join(f"pct_{pil} REAL" for pil in PILLARS)
    conn = get_db()
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS plantas (
            id TEXT PRIMARY KEY, name TEXT, site TEXT, customer TEXT, owner TEXT,
            problem TEXT, area TEXT, pais TEXT, areas_json TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT, planta_id TEXT,
            fecha TEXT, area TEXT, auditor TEXT, respuestas_json TEXT, notes TEXT,
            pct_total REAL, {audit_pct_cols}, clasificacion TEXT, evidencia TEXT
        );
        CREATE TABLE IF NOT EXISTS hallazgos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, planta_id TEXT,
            date TEXT, area TEXT, pillar TEXT, description TEXT, severity TEXT, status TEXT,
            corrective_action TEXT, responsible TEXT, due_date TEXT, evidencia TEXT
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT, planta_id TEXT,
            filename TEXT, caption TEXT, date TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT, password_hash TEXT, role TEXT
        );
        CREATE TABLE IF NOT EXISTS catalogo (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fase TEXT, descripcion TEXT
        );
        CREATE TABLE IF NOT EXISTS paises_plantas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pais TEXT, planta TEXT, areas_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_auditorias_pid ON auditorias(planta_id);
        CREATE INDEX IF NOT EXISTS idx_hallazgos_pid ON hallazgos(planta_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_pid ON evidence(planta_id);
    """)
    conn.commit()
    conn.close()


def migrate_json_to_sqlite_if_needed():
    """Migracion unica: si SQLite esta vacio y existen los JSON viejos,
    importa todo para no perder datos ya guardados en produccion."""
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS c FROM plantas").fetchone()["c"]
    conn.close()
    if existing > 0 or not PLANTAS_FILE.exists():
        pass
    else:
        try:
            old_plantas = json.loads(PLANTAS_FILE.read_text(encoding="utf-8"))
        except Exception:
            old_plantas = []
        conn = get_db()
        for p in old_plantas:
            conn.execute(
                "INSERT OR IGNORE INTO plantas (id,name,site,customer,owner,problem,area,pais,areas_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (p.get("id"), p.get("name", ""), p.get("site", ""), p.get("customer", ""), p.get("owner", ""),
                 p.get("problem", ""), p.get("area", "Logística"), p.get("pais", ""),
                 json.dumps(p.get("areas", [])), p.get("created_at", ""), p.get("updated_at", "")),
            )
            for a in p.get("auditorias", []):
                cols = _AUDIT_FLAT_COLS + ["respuestas_json"]
                vals = [a.get(c, "") for c in _AUDIT_FLAT_COLS] + [json.dumps(a.get("respuestas", []))]
                conn.execute(
                    f"INSERT INTO auditorias (planta_id,{','.join(cols)}) VALUES (?,{','.join('?' * len(cols))})",
                    (p.get("id"), *vals),
                )
            for h in p.get("hallazgos", []):
                conn.execute(
                    f"INSERT INTO hallazgos (planta_id,{','.join(_HALLAZGO_COLS)}) "
                    f"VALUES (?,{','.join('?' * len(_HALLAZGO_COLS))})",
                    (p.get("id"), *[h.get(c, "") for c in _HALLAZGO_COLS]),
                )
            for ev in p.get("evidence", []):
                conn.execute(
                    "INSERT INTO evidence (planta_id,filename,caption,date) VALUES (?,?,?,?)",
                    (p.get("id"), ev.get("filename", ""), ev.get("caption", ""), ev.get("date", "")),
                )
        conn.commit()
        conn.close()
        print(f"[Migración] {len(old_plantas)} planta(s) importada(s) de JSON a SQLite ({DB_FILE})")

    # Usuarios, catalogo y paises_plantas (migracion independiente, uno por uno)
    conn = get_db()
    has_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    old_users_file = DATA_DIR / "usuarios_5s.json"
    if has_users == 0 and old_users_file.exists():
        try:
            old_users = json.loads(old_users_file.read_text(encoding="utf-8"))
            conn = get_db()
            for u in old_users:
                conn.execute("INSERT OR IGNORE INTO users (id,email,password_hash,role) VALUES (?,?,?,?)",
                             (u.get("id"), u.get("email"), u.get("password_hash"), u.get("role", "user")))
            conn.commit()
            conn.close()
        except Exception:
            pass

    conn = get_db()
    has_cat = conn.execute("SELECT COUNT(*) c FROM catalogo").fetchone()["c"]
    conn.close()
    old_cat_file = DATA_DIR / "catalogo_5s.json"
    if has_cat == 0 and old_cat_file.exists():
        try:
            old_cat = json.loads(old_cat_file.read_text(encoding="utf-8"))
            conn = get_db()
            for c in old_cat:
                conn.execute("INSERT INTO catalogo (fase,descripcion) VALUES (?,?)",
                             (c.get("fase", ""), c.get("descripcion", "")))
            conn.commit()
            conn.close()
        except Exception:
            pass

    conn = get_db()
    has_pp = conn.execute("SELECT COUNT(*) c FROM paises_plantas").fetchone()["c"]
    conn.close()
    old_pp_file = DATA_DIR / "paises_plantas.json"
    if has_pp == 0 and old_pp_file.exists():
        try:
            old_pp = json.loads(old_pp_file.read_text(encoding="utf-8"))
            conn = get_db()
            for r in old_pp:
                conn.execute("INSERT INTO paises_plantas (pais,planta,areas_json) VALUES (?,?,?)",
                             (r.get("pais", ""), r.get("planta", ""), json.dumps(r.get("areas", []))))
            conn.commit()
            conn.close()
        except Exception:
            pass


def _nth_row_id(conn, table, pid, idx, pid_col="planta_id"):
    row = conn.execute(
        f"SELECT id FROM {table} WHERE {pid_col}=? ORDER BY id LIMIT 1 OFFSET ?", (pid, idx)
    ).fetchone()
    return row["id"] if row else None


def touch_planta_db(pid):
    conn = get_db()
    conn.execute("UPDATE plantas SET updated_at=? WHERE id=?",
                 (datetime.now().strftime("%d/%m/%Y %H:%M"), pid))
    conn.commit()
    conn.close()


def get_planta_dict(pid):
    conn = get_db()
    prow = conn.execute("SELECT * FROM plantas WHERE id=?", (pid,)).fetchone()
    if not prow:
        conn.close()
        return None
    p = dict(prow)
    p["areas"] = json.loads(p.pop("areas_json") or "[]")
    auditorias = []
    for r in conn.execute("SELECT * FROM auditorias WHERE planta_id=? ORDER BY id", (pid,)):
        d = dict(r)
        d["respuestas"] = json.loads(d.pop("respuestas_json") or "[]")
        auditorias.append(d)
    p["auditorias"] = auditorias
    p["hallazgos"] = [dict(r) for r in conn.execute(
        "SELECT * FROM hallazgos WHERE planta_id=? ORDER BY id", (pid,))]
    p["evidence"] = [dict(r) for r in conn.execute(
        "SELECT * FROM evidence WHERE planta_id=? ORDER BY id", (pid,))]
    conn.close()
    return p


def load_plantas():
    conn = get_db()
    ids = [r["id"] for r in conn.execute("SELECT id FROM plantas ORDER BY rowid ASC")]
    conn.close()
    return [get_planta_dict(pid) for pid in ids]


def create_planta_db(name, site, customer, owner, problem, area="Logística", pais="", areas=None):
    pid = gen_id()
    now = date.today().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO plantas (id,name,site,customer,owner,problem,area,pais,areas_json,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pid, name or "Nueva planta 5S", site, customer, owner, problem,
         area if area in AREAS else "Logística", pais or "", json.dumps(areas or []), now, now),
    )
    conn.commit()
    conn.close()
    return pid


def update_planta_db(pid, name, site, customer, owner, problem, area, pais, areas):
    conn = get_db()
    conn.execute(
        "UPDATE plantas SET name=?,site=?,customer=?,owner=?,problem=?,area=?,pais=?,areas_json=?,updated_at=? "
        "WHERE id=?",
        (name, site, customer, owner, problem, area, pais, json.dumps(areas or []),
         datetime.now().strftime("%d/%m/%Y %H:%M"), pid),
    )
    conn.commit()
    conn.close()


def delete_planta_db(pid):
    conn = get_db()
    for table in ("auditorias", "hallazgos", "evidence"):
        conn.execute(f"DELETE FROM {table} WHERE planta_id=?", (pid,))
    conn.execute("DELETE FROM plantas WHERE id=?", (pid,))
    conn.commit()
    conn.close()


def add_auditoria_db(pid, item):
    conn = get_db()
    cols = _AUDIT_FLAT_COLS + ["respuestas_json"]
    vals = [item.get(c, "") for c in _AUDIT_FLAT_COLS] + [json.dumps(item.get("respuestas", []))]
    placeholders = ",".join("?" * (len(cols) + 1))
    conn.execute(f"INSERT INTO auditorias (planta_id,{','.join(cols)}) VALUES ({placeholders})", (pid, *vals))
    conn.commit()
    conn.close()
    touch_planta_db(pid)


def update_auditoria_db(pid, idx, item):
    conn = get_db()
    real_id = _nth_row_id(conn, "auditorias", pid, idx)
    if real_id is not None:
        cols = _AUDIT_FLAT_COLS + ["respuestas_json"]
        vals = [item.get(c, "") for c in _AUDIT_FLAT_COLS] + [json.dumps(item.get("respuestas", []))]
        set_clause = ",".join(f"{c}=?" for c in cols)
        conn.execute(f"UPDATE auditorias SET {set_clause} WHERE id=?", (*vals, real_id))
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def delete_auditoria_db(pid, idx):
    conn = get_db()
    real_id = _nth_row_id(conn, "auditorias", pid, idx)
    if real_id is not None:
        conn.execute("DELETE FROM auditorias WHERE id=?", (real_id,))
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def add_hallazgo_db(pid, item):
    conn = get_db()
    placeholders = ",".join("?" * (len(_HALLAZGO_COLS) + 1))
    conn.execute(f"INSERT INTO hallazgos (planta_id,{','.join(_HALLAZGO_COLS)}) VALUES ({placeholders})",
                 (pid, *[item.get(c, "") for c in _HALLAZGO_COLS]))
    conn.commit()
    conn.close()
    touch_planta_db(pid)


def update_hallazgo_db(pid, idx, item):
    conn = get_db()
    real_id = _nth_row_id(conn, "hallazgos", pid, idx)
    if real_id is not None:
        set_clause = ",".join(f"{c}=?" for c in _HALLAZGO_COLS)
        conn.execute(f"UPDATE hallazgos SET {set_clause} WHERE id=?",
                     (*[item.get(c, "") for c in _HALLAZGO_COLS], real_id))
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def delete_hallazgo_db(pid, idx):
    conn = get_db()
    real_id = _nth_row_id(conn, "hallazgos", pid, idx)
    if real_id is not None:
        conn.execute("DELETE FROM hallazgos WHERE id=?", (real_id,))
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def close_hallazgo_db(pid, idx):
    conn = get_db()
    real_id = _nth_row_id(conn, "hallazgos", pid, idx)
    if real_id is not None:
        conn.execute("UPDATE hallazgos SET status='Cerrado' WHERE id=?", (real_id,))
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def bulk_delete_hallazgos_db(pid, idxs):
    conn = get_db()
    rows = conn.execute("SELECT id FROM hallazgos WHERE planta_id=? ORDER BY id", (pid,)).fetchall()
    ids_to_delete = [rows[i]["id"] for i in idxs if 0 <= i < len(rows)]
    if ids_to_delete:
        placeholders = ",".join("?" * len(ids_to_delete))
        conn.execute(f"DELETE FROM hallazgos WHERE id IN ({placeholders})", ids_to_delete)
        conn.commit()
    conn.close()
    touch_planta_db(pid)


def add_evidence_db(pid, filename, caption, ev_date):
    conn = get_db()
    conn.execute("INSERT INTO evidence (planta_id,filename,caption,date) VALUES (?,?,?,?)",
                 (pid, filename, caption, ev_date))
    conn.commit()
    conn.close()
    touch_planta_db(pid)


def delete_evidence_db(pid, filename):
    conn = get_db()
    conn.execute("DELETE FROM evidence WHERE planta_id=? AND filename=?", (pid, filename))
    conn.commit()
    conn.close()
    touch_planta_db(pid)


def load_users():
    conn = get_db()
    users = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY rowid ASC")]
    conn.close()
    return users


def save_users(users):
    conn = get_db()
    conn.execute("DELETE FROM users")
    for u in users:
        conn.execute("INSERT INTO users (id,email,password_hash,role) VALUES (?,?,?,?)",
                     (u["id"], u["email"], u["password_hash"], u.get("role", "user")))
    conn.commit()
    conn.close()


def load_catalogo():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT fase, descripcion FROM catalogo ORDER BY rowid ASC")]
    conn.close()
    return rows if rows else DEFAULT_CATALOGO


def save_catalogo(data):
    conn = get_db()
    conn.execute("DELETE FROM catalogo")
    for c in data:
        conn.execute("INSERT INTO catalogo (fase,descripcion) VALUES (?,?)",
                     (c.get("fase", ""), c.get("descripcion", "")))
    conn.commit()
    conn.close()


def load_paises_plantas():
    conn = get_db()
    rows = []
    for r in conn.execute("SELECT * FROM paises_plantas ORDER BY rowid ASC"):
        d = dict(r)
        d["areas"] = json.loads(d.pop("areas_json") or "[]")
        rows.append(d)
    conn.close()
    return rows


def save_paises_plantas(data):
    conn = get_db()
    conn.execute("DELETE FROM paises_plantas")
    for r in data:
        conn.execute("INSERT INTO paises_plantas (pais,planta,areas_json) VALUES (?,?,?)",
                     (r.get("pais", ""), r.get("planta", ""), json.dumps(r.get("areas", []))))
    conn.commit()
    conn.close()

app = Flask(__name__)
app.jinja_loader = DictLoader(TEMPLATES)
app.secret_key = os.environ.get("SECRET_KEY", "nefab-5s-web-dev-only")

init_db()
migrate_json_to_sqlite_if_needed()


app.jinja_env.globals.update(
    tr=tr, AREA_COLOR=AREA_COLOR, AREAS=AREAS, PILLARS=PILLARS, PILLAR_LABELS=PILLAR_LABELS,
    SCORE_OPTIONS=SCORE_OPTIONS, SEVERITIES=SEVERITIES, FINDING_STATUSES=FINDING_STATUSES,
    FASES=FASES, FASE_KEYS=FASE_KEYS, FASE_COLOR=FASE_COLOR, PREGUNTAS=PREGUNTAS,
    DEFAULT_CATALOGO=DEFAULT_CATALOGO,
    NB=NB, NO=NO, NG=NG, NGR=NGR, BG=BG, CARD=CARD, BORDER=BORDER,
    DARK=DARK, MUTED=MUTED, WHITE=WHITE, RED=RED, NBL=NBL,
)


@app.route("/style.css")
def style_css():
    return Response(STYLE_CSS, mimetype="text/css")


@app.route("/logo.png")
def logo_png():
    return Response(base64.b64decode(NEFAB_LOGO_B64), mimetype="image/png")


# ── Usuarios y sesión (login + roles admin/usuario) ─────────────────────────
# Nota: load_users/save_users/load_catalogo/save_catalogo/load_paises_plantas/
# save_paises_plantas ya estan definidos mas arriba (backend SQLite).
def get_user_by_id(uid):
    return next((u for u in load_users() if u["id"] == uid), None)


def get_user_by_email(email):
    email = (email or "").strip().lower()
    return next((u for u in load_users() if u["email"].lower() == email), None)


def user_initials(email):
    name_part = (email or "?").split("@")[0]
    parts = [p for p in name_part.replace(".", " ").replace("_", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name_part[:2].upper() if name_part else "??"


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    u = get_user_by_id(uid)
    if not u:
        return None
    return {"id": u["id"], "email": u["email"], "role": u.get("role", "user"), "initials": user_initials(u["email"])}


@app.context_processor
def inject_current_user():
    return {"current_user": get_current_user()}


def gen_id():
    return f"{int(time.time()*1000)}{''.join(random.choices(string.ascii_lowercase, k=4))}"


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not load_users():
            return redirect(url_for("setup"))
        if not session.get("user_id") or not get_user_by_id(session["user_id"]):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not load_users():
            return redirect(url_for("setup"))
        user = get_current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if load_users():
        return redirect(url_for("login"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or "@" not in email:
            error = "Ingresa un correo válido."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        else:
            users = [{
                "id": gen_id(), "email": email,
                "password_hash": generate_password_hash(password),
                "role": "admin",
            }]
            save_users(users)
            session["user_id"] = users[0]["id"]
            return redirect(url_for("plantas_list"))
    return render_template("setup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not load_users():
        return redirect(url_for("setup"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            next_url = request.args.get("next") or url_for("plantas_list")
            return redirect(next_url)
        error = "Correo o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template("admin_users.html", users=load_users(), current=get_current_user())


@app.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_user_new():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        role = role if role in ("admin", "user") else "user"
        if not email or "@" not in email:
            error = "Ingresa un correo válido."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif get_user_by_email(email):
            error = "Ya existe un usuario con ese correo."
        else:
            users = load_users()
            users.append({
                "id": gen_id(), "email": email,
                "password_hash": generate_password_hash(password),
                "role": role,
            })
            save_users(users)
            return redirect(url_for("admin_users"))
    return render_template("admin_user_form.html", error=error)


@app.route("/admin/users/<uid>/delete", methods=["POST"])
@admin_required
def admin_user_delete(uid):
    users = load_users()
    target = next((u for u in users if u["id"] == uid), None)
    if target:
        admins_left = sum(1 for u in users if u.get("role") == "admin" and u["id"] != uid)
        if target.get("role") == "admin" and admins_left == 0:
            return redirect(url_for("admin_users"))
        if target["id"] == session.get("user_id"):
            return redirect(url_for("admin_users"))
        users = [u for u in users if u["id"] != uid]
        save_users(users)
    return redirect(url_for("admin_users"))


@app.route("/set_lang/<lang>")
def set_lang(lang):
    session["lang"] = lang if lang in ("es", "en", "pt") else "es"
    return redirect(request.referrer or url_for("plantas_list"))


# ── Nota: load_plantas/get_planta_dict/create_planta_db/etc. ya estan
# definidos mas arriba (backend SQLite).
def all_hallazgos_flat():
    """Aplana los hallazgos de todas las plantas en una sola lista, con
    pais/planta/planta_id agregados, para el Cronograma global."""
    out = []
    for p in load_plantas():
        for idx, h in enumerate(p.get("hallazgos", [])):
            item = dict(h)
            item["planta_id"] = p["id"]
            item["planta_name"] = p.get("name", "")
            item["pais"] = p.get("pais", "")
            item["_idx"] = idx
            out.append(item)
    return out


def get_planta_or_404(pid):
    p = get_planta_dict(pid)
    if not p:
        abort(404)
    return None, p


def to_num(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return 0.0


def audit_avg(a):
    """Compatibilidad: si la auditoria tiene 'pct_total' (checklist nuevo) lo
    usa; si no, calcula desde 'respuestas' directamente."""
    if "pct_total" in a:
        return round(to_num(a.get("pct_total")), 1)
    respuestas = a.get("respuestas", [])
    if not respuestas:
        return 0.0
    return round(sum(respuestas) / len(respuestas) * 100, 1)


def clasificacion_pct(pct):
    if pct >= 80:
        return "Bueno"
    if pct >= 60:
        return "Regular"
    return "Bajo"


CLASIFICACION_LABEL = {
    "Bueno": "🟢 BUENO", "Regular": "🟡 REGULAR", "Bajo": "🔴 BAJO",
}
CLASIFICACION_COLOR = {"Bueno": NG, "Regular": "#FDD835", "Bajo": RED}


def compute_auditoria(respuestas, area, auditor, fecha, notes=""):
    """Dado un checklist de 10 respuestas (0/1), calcula pct_total y pct por
    fase, exactamente igual que la app de escritorio."""
    total_pts = sum(respuestas)
    pct_total = round(total_pts / len(respuestas) * 100, 1) if respuestas else 0.0
    pcts = {}
    for fase, idxs in FASES_MAP_IDX.items():
        vals = [respuestas[i] for i in idxs if i < len(respuestas)]
        pcts[fase] = round(sum(vals) / len(vals) * 100, 1) if vals else 0.0
    item = {
        "fecha": fecha, "area": area, "auditor": auditor,
        "pct_total": pct_total, "respuestas": respuestas, "notes": notes,
    }
    for f, v in pcts.items():
        item[f"pct_{f}"] = v
    item["clasificacion"] = clasificacion_pct(pct_total)
    return item


def planta_stats(p):
    """KPIs del dashboard + desgloses para los 3 paneles equivalentes a los
    donuts de la app de escritorio: resultados de auditoria (Bueno/Regular/
    Bajo), hallazgos por fase, y estado de hallazgos."""
    auditorias = p.get("auditorias", [])
    hallazgos = p.get("hallazgos", [])

    if auditorias:
        promedio = round(sum(audit_avg(a) for a in auditorias) / len(auditorias), 1)
        ultima = auditorias[-1]
        pilares = {pil: to_num(ultima.get(f"pct_{pil}", 0)) for pil in PILLARS}
    else:
        promedio = 0.0
        pilares = {pil: 0.0 for pil in PILLARS}

    resultado_counts = {"Bueno": 0, "Regular": 0, "Bajo": 0}
    for a in auditorias:
        clas = a.get("clasificacion") or clasificacion_pct(audit_avg(a))
        resultado_counts[clas] = resultado_counts.get(clas, 0) + 1

    fase_counts = {f: 0 for f in FASES}
    for h in hallazgos:
        fase = h.get("fase", "")
        if fase in fase_counts:
            fase_counts[fase] += 1

    estado_counts = {"Abierto": 0, "En progreso": 0, "Cerrado": 0}
    for h in hallazgos:
        est = h.get("status", "Abierto")
        estado_counts[est] = estado_counts.get(est, 0) + 1

    abiertos = sum(1 for h in hallazgos if h.get("status") != "Cerrado")
    cerrados = sum(1 for h in hallazgos if h.get("status") == "Cerrado")
    return {
        "promedio": promedio, "num_auditorias": len(auditorias),
        "abiertos": abiertos, "cerrados": cerrados, "total_hallazgos": len(hallazgos),
        "pilares": pilares, "resultado_counts": resultado_counts,
        "fase_counts": fase_counts, "estado_counts": estado_counts,
    }


app.jinja_env.globals.update(
    audit_avg=audit_avg, clasificacion_pct=clasificacion_pct,
    CLASIFICACION_LABEL=CLASIFICACION_LABEL, CLASIFICACION_COLOR=CLASIFICACION_COLOR,
)


# ── Lista de plantas ─────────────────────────────────────────────────────
@app.route("/")
@login_required
def plantas_list():
    plantas = load_plantas()
    area_filter = request.args.get("area", "Todos")
    total = len(plantas)
    n_log = sum(1 for p in plantas if p.get("area", "Logística") == "Logística")
    n_man = sum(1 for p in plantas if p.get("area", "Logística") == "Manufactura")
    visible = [
        p for p in reversed(plantas)
        if area_filter == "Todos" or p.get("area", "Logística") == area_filter
    ]
    for p in visible:
        auditorias = p.get("auditorias", [])
        p["_num_auditorias"] = len(auditorias)
        p["_promedio"] = round(sum(audit_avg(a) for a in auditorias) / len(auditorias), 1) if auditorias else 0.0
    return render_template(
        "plantas_list.html", plantas=visible, area_filter=area_filter,
        total=total, n_log=n_log, n_man=n_man,
    )


@app.route("/planta/new", methods=["GET", "POST"])
@login_required
def new_planta_view():
    if request.method == "POST":
        areas_raw = request.form.get("areas", "").strip()
        areas_list = [a.strip() for a in areas_raw.split(",") if a.strip()]
        pid = create_planta_db(
            request.form.get("name", "").strip(),
            request.form.get("site", "").strip(),
            request.form.get("customer", "").strip(),
            request.form.get("owner", "").strip(),
            request.form.get("problem", "").strip(),
            area=request.form.get("area", "Logística"),
            pais=request.form.get("pais", "").strip(),
            areas=areas_list,
        )
        return redirect(url_for("planta_overview", pid=pid))
    return render_template("planta_form.html", old={}, registro=load_paises_plantas())


@app.route("/planta/<pid>/edit", methods=["GET", "POST"])
@login_required
def edit_planta_view(pid):
    _, p = get_planta_or_404(pid)
    if request.method == "POST":
        areas_raw = request.form.get("areas", "").strip()
        areas_list = [a.strip() for a in areas_raw.split(",") if a.strip()]
        update_planta_db(
            pid,
            request.form.get("name", "").strip() or p["name"],
            request.form.get("site", "").strip(),
            request.form.get("customer", "").strip(),
            request.form.get("owner", "").strip(),
            request.form.get("problem", "").strip(),
            request.form.get("area", p.get("area", "Logística")),
            request.form.get("pais", "").strip(),
            areas_list,
        )
        return redirect(url_for("planta_overview", pid=pid))
    return render_template("planta_form.html", old=p, registro=load_paises_plantas())


@app.route("/planta/<pid>/delete", methods=["POST"])
@login_required
def delete_planta(pid):
    delete_planta_db(pid)
    try:
        import shutil
        shutil.rmtree(PHOTOS_DIR / pid, ignore_errors=True)
    except Exception:
        pass
    return redirect(url_for("plantas_list"))


@app.route("/planta/<pid>")
@login_required
def planta_home(pid):
    return redirect(url_for("planta_overview", pid=pid))


@app.route("/planta/<pid>/overview")
@login_required
def planta_overview(pid):
    _, p = get_planta_or_404(pid)
    stats = planta_stats(p)
    return render_template("planta_overview.html", p=p, stats=stats, active="Inicio")


# ── Auditorías 5S ────────────────────────────────────────────────────────
@app.route("/planta/<pid>/auditorias")
@login_required
def planta_auditorias(pid):
    _, p = get_planta_or_404(pid)
    return render_template("planta_auditorias.html", p=p, active="Auditorías")


@app.route("/planta/<pid>/auditorias/save", methods=["GET", "POST"])
@login_required
def auditoria_form(pid):
    _, p = get_planta_or_404(pid)
    idx = request.args.get("idx", type=int)
    old = p["auditorias"][idx] if idx is not None and 0 <= idx < len(p["auditorias"]) else {}
    if request.method == "POST":
        respuestas = []
        for i in range(len(PREGUNTAS)):
            respuestas.append(1 if request.form.get(f"q{i}") == "1" else 0)
        item = compute_auditoria(
            respuestas,
            area=request.form.get("area", "").strip(),
            auditor=request.form.get("auditor", "").strip(),
            fecha=request.form.get("date", "").strip() or date.today().isoformat(),
            notes=request.form.get("notes", "").strip(),
        )
        if idx is not None and old.get("evidencia"):
            item["evidencia"] = old["evidencia"]

        file = request.files.get("photo")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext in ALLOWED_PHOTO_EXT:
                planta_photo_dir = PHOTOS_DIR / pid
                planta_photo_dir.mkdir(parents=True, exist_ok=True)
                unique_name = secure_filename(
                    f"audit_{int(time.time()*1000)}{''.join(random.choices(string.ascii_lowercase, k=4))}.{ext}"
                )
                file.save(str(planta_photo_dir / unique_name))
                item["evidencia"] = unique_name
                add_evidence_db(pid, unique_name, f"Auditoría {item['fecha']} — {item.get('area','')}",
                                 date.today().isoformat())

        if idx is not None:
            update_auditoria_db(pid, idx, item)
        else:
            add_auditoria_db(pid, item)
        return redirect(url_for("planta_auditorias", pid=pid))
    return render_template("auditoria_form.html", p=p, old=old, idx=idx)


@app.route("/planta/<pid>/auditorias/<int:idx>/delete", methods=["POST"])
@login_required
def auditoria_delete(pid, idx):
    delete_auditoria_db(pid, idx)
    return redirect(url_for("planta_auditorias", pid=pid))


# ── Hallazgos 5S ─────────────────────────────────────────────────────────
@app.route("/planta/<pid>/hallazgos")
@login_required
def planta_hallazgos(pid):
    _, p = get_planta_or_404(pid)
    return render_template("planta_hallazgos.html", p=p, active="Hallazgos")


@app.route("/planta/<pid>/hallazgos/save", methods=["GET", "POST"])
@login_required
def hallazgo_form(pid):
    _, p = get_planta_or_404(pid)
    idx = request.args.get("idx", type=int)
    old = p["hallazgos"][idx] if idx is not None and 0 <= idx < len(p["hallazgos"]) else {}
    if request.method == "POST":
        item = {
            "date": request.form.get("date", "").strip(),
            "area": request.form.get("area", "").strip(),
            "pillar": request.form.get("pillar", FASES[0]),
            "description": request.form.get("description", "").strip(),
            "severity": request.form.get("severity", SEVERITIES[0]),
            "status": request.form.get("status", FINDING_STATUSES[0]),
            "corrective_action": request.form.get("corrective_action", "").strip(),
            "responsible": request.form.get("responsible", "").strip(),
            "due_date": request.form.get("due_date", "").strip(),
        }
        if not item["area"]:
            return render_template("hallazgo_form.html", p=p, old=item, idx=idx, error=True, catalogo=load_catalogo())
        if idx is not None and old.get("evidencia"):
            item["evidencia"] = old["evidencia"]

        file = request.files.get("photo")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext in ALLOWED_PHOTO_EXT:
                planta_photo_dir = PHOTOS_DIR / pid
                planta_photo_dir.mkdir(parents=True, exist_ok=True)
                unique_name = secure_filename(
                    f"hallazgo_{int(time.time()*1000)}{''.join(random.choices(string.ascii_lowercase, k=4))}.{ext}"
                )
                file.save(str(planta_photo_dir / unique_name))
                item["evidencia"] = unique_name
                add_evidence_db(pid, unique_name,
                                 f"Hallazgo — {item.get('area','')}: {item.get('description','')[:60]}",
                                 date.today().isoformat())

        if idx is not None:
            update_hallazgo_db(pid, idx, item)
        else:
            add_hallazgo_db(pid, item)
        return redirect(url_for("planta_hallazgos", pid=pid))
    return render_template("hallazgo_form.html", p=p, old=old, idx=idx, error=False, catalogo=load_catalogo())


@app.route("/planta/<pid>/hallazgos/<int:idx>/delete", methods=["POST"])
@login_required
def hallazgo_delete(pid, idx):
    delete_hallazgo_db(pid, idx)
    return redirect(url_for("planta_hallazgos", pid=pid))


@app.route("/planta/<pid>/hallazgos/<int:idx>/close", methods=["POST"])
@login_required
def hallazgo_close(pid, idx):
    close_hallazgo_db(pid, idx)
    return redirect(url_for("planta_hallazgos", pid=pid))


@app.route("/planta/<pid>/hallazgos/bulk_delete", methods=["POST"])
@login_required
def hallazgos_bulk_delete(pid):
    idxs = {int(i) for i in request.form.getlist("idx")}
    bulk_delete_hallazgos_db(pid, idxs)
    return redirect(url_for("planta_hallazgos", pid=pid))


# ── Catálogo global de posibilidades (compartido entre todas las plantas) ──
@app.route("/cronograma")
@login_required
def cronograma_view():
    hallazgos = all_hallazgos_flat()

    paises = sorted({h.get("pais", "") for h in hallazgos if h.get("pais")})

    pais_f = request.args.get("pais", "")
    estado_f = request.args.get("estado", "")
    fase_f = request.args.get("fase", "")
    hoy = date.today()
    date_from_s = request.args.get("date_from", "") or (hoy - timedelta(days=28)).isoformat()
    date_to_s = request.args.get("date_to", "") or hoy.isoformat()

    try:
        date_from = datetime.strptime(date_from_s, "%Y-%m-%d").date()
    except Exception:
        date_from = hoy - timedelta(days=28)
    try:
        date_to = datetime.strptime(date_to_s, "%Y-%m-%d").date()
    except Exception:
        date_to = hoy
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    filtered = []
    for h in hallazgos:
        if pais_f and h.get("pais") != pais_f:
            continue
        if estado_f and h.get("status") != estado_f:
            continue
        if fase_f and h.get("pillar") != fase_f:
            continue
        h_date_s = h.get("date", "")
        try:
            h_date = datetime.strptime(h_date_s, "%Y-%m-%d").date()
        except Exception:
            continue
        if h_date < date_from or h_date > date_to:
            continue
        filtered.append((h, h_date))

    # Semanas ISO en el rango, con etiqueta "S<numero>"
    weeks = []
    cur = date_from - timedelta(days=date_from.weekday())  # lunes de esa semana
    end_monday = date_to - timedelta(days=date_to.weekday())
    hoy_monday = hoy - timedelta(days=hoy.weekday())
    while cur <= end_monday:
        iso_week = cur.isocalendar()[1]
        weeks.append({
            "label": f"S{iso_week}",
            "start": cur, "end": cur + timedelta(days=6),
            "is_current": cur == hoy_monday,
        })
        cur += timedelta(days=7)
    if not weeks:
        iso_week = hoy_monday.isocalendar()[1]
        weeks = [{"label": f"S{iso_week}", "start": hoy_monday, "end": hoy_monday, "is_current": True}]

    rows = []
    for h, h_date in filtered:
        week_idx = None
        for i, w in enumerate(weeks):
            if w["start"] <= h_date <= w["end"]:
                week_idx = i
                break
        rows.append({
            "area": h.get("area", ""), "description": h.get("description", ""),
            "status": h.get("status", "Abierto"), "pillar": h.get("pillar", ""),
            "planta_name": h.get("planta_name", ""), "pais": h.get("pais", ""),
            "week_idx": week_idx,
        })

    return render_template(
        "cronograma.html", weeks=weeks, rows=rows, paises=paises,
        pais_f=pais_f, estado_f=estado_f, fase_f=fase_f,
        date_from=date_from.isoformat(), date_to=date_to.isoformat(),
    )


@app.route("/catalogo")
@login_required
def catalogo_view():
    pid = request.args.get("pid", "")
    catalogo = load_catalogo()
    grouped = {f: [] for f in FASES}
    for real_idx, c in enumerate(catalogo):
        fase = c.get("fase")
        if fase in grouped:
            grouped[fase].append((real_idx, c))
    edit_idx = request.args.get("edit_idx", type=int)
    edit_item = catalogo[edit_idx] if edit_idx is not None and 0 <= edit_idx < len(catalogo) else None
    return render_template("catalogo.html", grouped=grouped, pid=pid, edit_idx=edit_idx, edit_item=edit_item)


@app.route("/catalogo/add", methods=["POST"])
@login_required
def catalogo_add():
    pid = request.form.get("pid", "")
    fase = request.form.get("fase", FASES[0])
    descripcion = request.form.get("descripcion", "").strip()
    idx_raw = request.form.get("idx", "")
    if descripcion:
        catalogo = load_catalogo()
        if idx_raw != "" and idx_raw.isdigit() and 0 <= int(idx_raw) < len(catalogo):
            catalogo[int(idx_raw)] = {"fase": fase, "descripcion": descripcion}
        else:
            catalogo.append({"fase": fase, "descripcion": descripcion})
        save_catalogo(catalogo)
    return redirect(url_for("catalogo_view", pid=pid))


@app.route("/catalogo/<int:idx>/delete", methods=["POST"])
@login_required
def catalogo_delete(idx):
    pid = request.args.get("pid", "") or request.form.get("pid", "")
    catalogo = load_catalogo()
    if 0 <= idx < len(catalogo):
        catalogo.pop(idx)
        save_catalogo(catalogo)
    return redirect(url_for("catalogo_view", pid=pid))


# ── Catálogo global de Países y Plantas (para dropdowns en cascada) ────────
@app.route("/paises-plantas")
@login_required
def paises_plantas_view():
    pid = request.args.get("pid", "")
    registro = load_paises_plantas()
    edit_idx = request.args.get("edit_idx", type=int)
    edit_item = registro[edit_idx] if edit_idx is not None and 0 <= edit_idx < len(registro) else None
    return render_template(
        "paises_plantas.html", registro=list(enumerate(registro)), pid=pid,
        edit_idx=edit_idx, edit_item=edit_item,
    )


@app.route("/paises-plantas/add", methods=["POST"])
@login_required
def paises_plantas_add():
    pid = request.form.get("pid", "")
    pais = request.form.get("pais", "").strip()
    planta = request.form.get("planta", "").strip()
    areas_raw = request.form.get("areas", "").strip()
    areas_list = [a.strip() for a in areas_raw.split(",") if a.strip()]
    idx_raw = request.form.get("idx", "")
    if pais and planta:
        registro = load_paises_plantas()
        item = {"pais": pais, "planta": planta, "areas": areas_list}
        if idx_raw != "" and idx_raw.isdigit() and 0 <= int(idx_raw) < len(registro):
            registro[int(idx_raw)] = item
        else:
            registro.append(item)
        save_paises_plantas(registro)
    return redirect(url_for("paises_plantas_view", pid=pid))


@app.route("/paises-plantas/<int:idx>/delete", methods=["POST"])
@login_required
def paises_plantas_delete(idx):
    pid = request.args.get("pid", "") or request.form.get("pid", "")
    registro = load_paises_plantas()
    if 0 <= idx < len(registro):
        registro.pop(idx)
        save_paises_plantas(registro)
    return redirect(url_for("paises_plantas_view", pid=pid))


# ── Evidencias fotográficas ────────────────────────────────────────────────
@app.route("/planta/<pid>/evidencia")
@login_required
def planta_evidencia(pid):
    _, p = get_planta_or_404(pid)
    return render_template("planta_evidencia.html", p=p, active="Evidencias")


@app.route("/planta/<pid>/evidencia/upload", methods=["POST"])
@login_required
def evidencia_upload(pid):
    file = request.files.get("photo")
    if not file or not file.filename:
        return redirect(url_for("planta_evidencia", pid=pid))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_PHOTO_EXT:
        return redirect(url_for("planta_evidencia", pid=pid))

    planta_photo_dir = PHOTOS_DIR / pid
    planta_photo_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{int(time.time()*1000)}{''.join(random.choices(string.ascii_lowercase, k=4))}.{ext}"
    safe_name = secure_filename(unique_name)
    file.save(str(planta_photo_dir / safe_name))

    add_evidence_db(pid, safe_name, request.form.get("caption", "").strip(), date.today().isoformat())
    return redirect(url_for("planta_evidencia", pid=pid))


@app.route("/planta/<pid>/evidencia/photo/<filename>")
@login_required
def evidencia_photo(pid, filename):
    planta_photo_dir = PHOTOS_DIR / pid
    safe_name = secure_filename(filename)
    if not (planta_photo_dir / safe_name).exists():
        abort(404)
    return send_from_directory(str(planta_photo_dir), safe_name)


@app.route("/planta/<pid>/evidencia/<filename>/delete", methods=["POST"])
@login_required
def evidencia_delete(pid, filename):
    safe_name = secure_filename(filename)
    delete_evidence_db(pid, safe_name)
    try:
        (PHOTOS_DIR / pid / safe_name).unlink(missing_ok=True)
    except Exception:
        pass
    return redirect(url_for("planta_evidencia", pid=pid))


# ── Exportar ──────────────────────────────────────────────────────────────
@app.route("/planta/<pid>/export")
@login_required
def planta_export(pid):
    _, p = get_planta_or_404(pid)
    return render_template("planta_export.html", p=p, active="Exportar")


@app.route("/planta/<pid>/export.zip")
@login_required
def planta_export_zip(pid):
    _, p = get_planta_or_404(pid)
    exports = {
        "auditorias_5s.csv": (
            ["Fecha", "Zona/Area", "Auditor"] + PILLARS + ["% General", "Clasificacion", "Observaciones"],
            p.get("auditorias", []),
        ),
        "hallazgos_5s.csv": (
            ["Fecha", "Zona/Area", "Fase", "Descripcion", "Severidad", "Accion correctiva",
             "Responsable", "Fecha compromiso", "Estado"],
            p.get("hallazgos", []),
        ),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Auditorias
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(exports["auditorias_5s.csv"][0])
        for a in exports["auditorias_5s.csv"][1]:
            clas = a.get("clasificacion") or clasificacion_pct(audit_avg(a))
            row = [a.get("fecha", ""), a.get("area", ""), a.get("auditor", "")] \
                + [a.get(f"pct_{pil}", "") for pil in PILLARS] \
                + [audit_avg(a), clas, a.get("notes", "")]
            writer.writerow(row)
        zf.writestr("auditorias_5s.csv", csv_buf.getvalue())
        # Hallazgos
        csv_buf2 = io.StringIO()
        writer2 = csv.writer(csv_buf2)
        writer2.writerow(exports["hallazgos_5s.csv"][0])
        for h in exports["hallazgos_5s.csv"][1]:
            writer2.writerow([
                h.get("date", ""), h.get("area", ""), h.get("pillar", ""), h.get("description", ""),
                h.get("severity", ""), h.get("corrective_action", ""), h.get("responsible", ""),
                h.get("due_date", ""), h.get("status", ""),
            ])
        zf.writestr("hallazgos_5s.csv", csv_buf2.getvalue())
    buf.seek(0)
    safe_name = "".join(c for c in p.get("name", "5s") if c.isalnum() or c in " _-").strip() or "5s"
    return send_file(buf, as_attachment=True, download_name=f"{safe_name}_export.zip", mimetype="application/zip")


def _pdf_safe(text):
    text = str(text if text is not None else "")
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_wrap_long_words(text, max_word_len=35):
    """fpdf2 lanza una excepcion (FPDFException) si una 'palabra' sin
    espacios es mas ancha que la linea disponible en multi_cell. Esto pasa
    facilmente con texto libre (ej. 'Problema / Alcance' escrito sin
    espacios, o una URL). Insertamos espacios cada N caracteres dentro de
    cualquier palabra demasiado larga para que siempre pueda partirse."""
    text = _pdf_safe(text)
    words = text.split(" ")
    out_words = []
    for w in words:
        if len(w) > max_word_len:
            chunks = [w[i:i + max_word_len] for i in range(0, len(w), max_word_len)]
            out_words.append(" ".join(chunks))
        else:
            out_words.append(w)
    return " ".join(out_words)


def _pdf_truncate(text, max_chars):
    text = _pdf_safe(text)
    if len(text) > max_chars:
        return text[: max(0, max_chars - 3)] + "..."
    return text


_PDF_BLUE = (20, 78, 140)
_PDF_ORANGE = (254, 130, 0)
_PDF_GREEN = (140, 194, 74)
_PDF_RED = (227, 73, 72)
_PDF_GRAY = (100, 100, 100)


def _pdf_header(pdf, title):
    pdf.set_fill_color(*_PDF_BLUE)
    pdf.rect(0, 0, pdf.w, 16, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(8, 3)
    _pdf_safe_cell(pdf, 140, 10, "NEFAB - 5S", 0, 0, "L")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(pdf.w - 110, 3)
    _pdf_safe_cell(pdf, 102, 10, _pdf_safe(title), 0, 0, "R")
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(20)


def _pdf_section_title(pdf, text):
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_PDF_BLUE)
    _pdf_safe_cell(pdf, 0, 8, _pdf_safe(text), 0, 1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def _pdf_safe_cell(pdf, w, h, text, border=0, ln=0, align="", fill=False):
    """Envoltorio a prueba de fallos sobre pdf.cell(): si fpdf2 no puede
    renderizar el texto en el ancho disponible ('Not enough horizontal
    space to render a single character'), en vez de tumbar todo el PDF,
    reintenta con un texto mas corto y como ultimo recurso deja la celda
    vacia."""
    try:
        pdf.cell(w, h, text, border, ln, align, fill)
    except Exception:
        try:
            pdf.cell(w, h, _pdf_truncate(text, 3), border, ln, align, fill)
        except Exception:
            try:
                pdf.cell(w, h, "", border, ln, align, fill)
            except Exception:
                pass


def _pdf_safe_multicell(pdf, w, h, text):
    try:
        pdf.multi_cell(w, h, text)
    except Exception:
        try:
            pdf.multi_cell(w, h, _pdf_truncate(text, 20))
        except Exception:
            try:
                pdf.multi_cell(w, h, "-")
            except Exception:
                pdf.ln(h)


def _pdf_table_row(pdf, cells, widths, height=7, header=False, fill=None):
    pdf.set_font("Helvetica", "B" if header else "", 8)
    if header:
        pdf.set_fill_color(*_PDF_BLUE)
        pdf.set_text_color(255, 255, 255)
        do_fill = True
    elif fill:
        pdf.set_fill_color(*fill)
        pdf.set_text_color(0, 0, 0)
        do_fill = True
    else:
        pdf.set_text_color(0, 0, 0)
        do_fill = False
    for text, w in zip(cells, widths):
        _pdf_safe_cell(pdf, w, height, _pdf_truncate(text, max(4, int(w / 1.7))), 1, 0, "L", do_fill)
    pdf.ln(height)
    pdf.set_text_color(0, 0, 0)


def generate_pdf_report(p):
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    _pdf_header(pdf, "Reporte 5S")

    area = p.get("area", "Logística")
    area_color = _PDF_BLUE if area == "Logística" else _PDF_ORANGE
    pdf.set_fill_color(*area_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    _pdf_safe_cell(pdf, 35, 7, _pdf_safe(area), 0, 1, "C", True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 16)
    _pdf_safe_cell(pdf, 0, 10, _pdf_truncate(p.get("name", ""), 70), 0, 1)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_PDF_GRAY)
    _pdf_safe_cell(pdf, 0, 6, _pdf_safe(f"{p.get('customer','')}  -  {p.get('site','')}  -  {p.get('created_at','')}"), 0, 1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    _pdf_section_title(pdf, "Información de la planta")
    info_rows = [
        ("Sitio / Operación", p.get("site", "") or "-"),
        ("Cliente", p.get("customer", "") or "-"),
        ("Responsable", p.get("owner", "") or "-"),
        ("Área", area),
        ("Problema / Alcance", p.get("problem", "") or "-"),
    ]
    for label, value in info_rows:
        pdf.set_font("Helvetica", "B", 9)
        _pdf_safe_cell(pdf, 45, 6, _pdf_safe(label), 0, 0)
        pdf.set_font("Helvetica", "", 9)
        y_before = pdf.get_y()
        _pdf_safe_multicell(pdf, 0, 6, _pdf_wrap_long_words(value))
        pdf.set_xy(pdf.l_margin, max(pdf.get_y(), y_before + 6))
    pdf.ln(3)

    stats = planta_stats(p)
    _pdf_section_title(pdf, "KPIs")
    kpi_items = [
        ("Promedio general", f"{stats['promedio']}%", _PDF_BLUE),
        ("Auditorías", str(stats["num_auditorias"]), _PDF_GRAY),
        ("Hallazgos abiertos", str(stats["abiertos"]), _PDF_RED),
        ("Hallazgos cerrados", str(stats["cerrados"]), _PDF_GREEN),
    ]
    box_w = 42
    x0, y0 = pdf.get_x(), pdf.get_y()
    for i, (label, value, color) in enumerate(kpi_items):
        x = x0 + i * (box_w + 2)
        pdf.set_draw_color(220, 220, 220)
        pdf.rect(x, y0, box_w, 18)
        pdf.set_xy(x, y0 + 3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*color)
        _pdf_safe_cell(pdf, box_w, 7, _pdf_safe(value), 0, 0, "C")
        pdf.set_xy(x, y0 + 11)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_PDF_GRAY)
        _pdf_safe_cell(pdf, box_w, 5, _pdf_safe(label), 0, 0, "C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + 24)

    _pdf_section_title(pdf, "Promedio por pilar")
    for pil in PILLARS:
        y = pdf.get_y()
        val = stats["pilares"].get(pil, 0)
        pdf.set_font("Helvetica", "", 9)
        _pdf_safe_cell(pdf, 55, 6, _pdf_safe(PILLAR_LABELS.get(pil, pil)), 0, 0)
        bar_w = max(1.0, 40.0 * (val / 100.0))
        color = _PDF_GREEN if val >= 80 else (_PDF_ORANGE if val >= 60 else _PDF_RED)
        pdf.set_fill_color(*color)
        pdf.rect(pdf.get_x(), y + 1, bar_w, 4, "F")
        pdf.set_xy(pdf.get_x() + 22, y)
        _pdf_safe_cell(pdf, 20, 6, f"{val}%", 0, 0)
        pdf.ln(6)
    pdf.ln(2)

    auditorias = p.get("auditorias", [])
    if auditorias:
        pdf.add_page(orientation="P")
        _pdf_header(pdf, "Auditorías 5S")
        card_w, card_h, gap = 190, 28, 4
        for a in auditorias:
            clas = a.get("clasificacion") or clasificacion_pct(audit_avg(a))
            clas_color = _PDF_GREEN if clas == "Bueno" else (_PDF_ORANGE if clas == "Regular" else _PDF_RED)
            y0 = pdf.get_y()
            if y0 + card_h > 275:
                pdf.add_page(orientation="P")
                _pdf_header(pdf, "Auditorías 5S (cont.)")
                y0 = pdf.get_y()

            pdf.set_draw_color(225, 229, 235)
            pdf.set_fill_color(250, 251, 253)
            pdf.rect(10, y0, card_w, card_h, "DF")

            # Encabezado: Área — País ................ Auditor | Fecha
            pdf.set_xy(13, y0 + 3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 0, 0)
            _pdf_safe_cell(pdf, 110, 6, _pdf_truncate(f"{a.get('area','') or '-'} — {p.get('pais','') or '-'}", 42), 0, 0)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_PDF_GRAY)
            pdf.set_xy(123, y0 + 3)
            _pdf_safe_cell(pdf, 64, 6, _pdf_truncate(f"Auditor: {a.get('auditor','-') or '-'} | {a.get('fecha','')}", 42), 0, 0, "R")
            pdf.set_text_color(0, 0, 0)

            # % General, grande, a la izquierda
            pdf.set_xy(13, y0 + 11)
            pdf.set_font("Helvetica", "B", 17)
            pdf.set_text_color(*clas_color)
            _pdf_safe_cell(pdf, 32, 10, f"{audit_avg(a)}%", 0, 0)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_xy(13, y0 + 21)
            pdf.set_text_color(*_PDF_GRAY)
            _pdf_safe_cell(pdf, 32, 5, "General", 0, 0)
            pdf.set_text_color(0, 0, 0)

            # Los 5 pilares, en columnas
            x = 50
            col_w = (card_w - 40) / len(PILLARS)
            for pil in PILLARS:
                val = a.get(f"pct_{pil}", 0)
                pdf.set_xy(x, y0 + 11)
                pdf.set_font("Helvetica", "B", 11)
                _pdf_safe_cell(pdf, col_w, 6, f"{val}%", 0, 0, "C")
                pdf.set_xy(x, y0 + 18)
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(*_PDF_GRAY)
                _pdf_safe_cell(pdf, col_w, 5, pil, 0, 0, "C")
                pdf.set_text_color(0, 0, 0)
                x += col_w

            pdf.set_y(y0 + card_h + gap)

    hallazgos = p.get("hallazgos", [])
    if hallazgos:
        pdf.add_page(orientation="L")
        _pdf_header(pdf, "Hallazgos 5S")
        widths = [22, 32, 22, 62, 20, 62, 30, 27]
        headers = ["Fecha", "Zona", "Pilar", "Descripción", "Sever.", "Acción correctiva", "Responsable", "Estado"]
        _pdf_table_row(pdf, headers, widths, header=True)
        for i, h in enumerate(hallazgos):
            row = [
                h.get("date", ""), h.get("area", ""), h.get("pillar", ""), h.get("description", ""),
                h.get("severity", ""), h.get("corrective_action", ""), h.get("responsible", ""), h.get("status", ""),
            ]
            _pdf_table_row(pdf, row, widths, fill=(245, 247, 250) if i % 2 else None)

    evidence = p.get("evidence", [])
    if evidence:
        pdf.add_page(orientation="P")
        _pdf_header(pdf, "Evidencia fotográfica")
        x, y = 10, 22
        col_w, col_h = 90, 70
        for ev in evidence:
            if x + col_w > 200:
                x = 10
                y += col_h + 8
            if y + col_h > 275:
                pdf.add_page(orientation="P")
                _pdf_header(pdf, "Evidencia fotográfica (cont.)")
                x, y = 10, 22
            photo_path = PHOTOS_DIR / p.get("id", "") / ev.get("filename", "")
            try:
                if photo_path.exists():
                    pdf.image(str(photo_path), x=x, y=y, w=col_w, h=col_h - 12)
            except Exception:
                pass
            pdf.set_xy(x, y + col_h - 11)
            pdf.set_font("Helvetica", "", 8)
            _pdf_safe_multicell(pdf, col_w, 4, _pdf_wrap_long_words(_pdf_truncate(ev.get("caption", "") or "-", 60), max_word_len=18))
            x += col_w + 10

    try:
        out = pdf.output(dest="S")
    except TypeError:
        out = pdf.output()
    if isinstance(out, str):
        out = out.encode("latin-1", errors="replace")
    elif isinstance(out, bytearray):
        out = bytes(out)
    return out


@app.route("/planta/<pid>/report.pdf")
@login_required
def planta_report_pdf(pid):
    _, p = get_planta_or_404(pid)
    try:
        pdf_bytes = generate_pdf_report(p)
    except ImportError:
        return Response(
            "Falta instalar fpdf2. En Pydroid 3: menu Pip -> busca 'fpdf2' -> instala. "
            "En PC: pip install fpdf2",
            status=500,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            "No se pudo generar el PDF de esta planta. Se registró el detalle en los "
            "logs del servidor para revisarlo. Error: " + _pdf_safe(str(e)),
            status=500,
        )
    safe_name = "".join(c for c in p.get("name", "5s") if c.isalnum() or c in " _-").strip() or "5s"
    return send_file(
        io.BytesIO(pdf_bytes), as_attachment=True,
        download_name=f"{safe_name}_reporte.pdf", mimetype="application/pdf",
    )


if __name__ == "__main__":
    print(f"[Diagnóstico] Carpeta de script: {Path(__file__).resolve().parent}")
    print(f"[Diagnóstico] DATA_DIR en uso: {DATA_DIR}")
    print(f"[Diagnóstico] PLANTAS_FILE: {PLANTAS_FILE}")
    # host 127.0.0.1: en Pydroid 3, abre el navegador en http://127.0.0.1:5000
    # debug=True: muestra el error real en el navegador si algo falla.
    # use_reloader=False: el reloader automatico de Flask puede fallar en Android
    # y tumbar el servidor tras la primera peticion, por eso lo desactivamos.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False, threaded=True)
