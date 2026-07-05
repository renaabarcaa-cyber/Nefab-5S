# Nefab 5S Manager Web

Versión web convertida desde la app Tkinter 5S Manager v3 para publicar en Render con GitHub.

## Ejecutar local

```bash
pip install -r requirements.txt
python app.py
```

Abrir: http://localhost:5000

## Publicar en Render

1. Crear un repositorio en GitHub.
2. Subir todos estos archivos.
3. Entrar a Render > New > Web Service.
4. Conectar el repositorio.
5. Render detectará `render.yaml` o usar:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
6. Deploy.

## Funciones incluidas

- Dashboard 5S
- Checklist de auditoría
- Cálculo por fase: Seiri, Seiton, Seiso, Seiketsu y Shitsuke
- Hallazgos/tickets con evidencia
- Cierre de hallazgos
- Cronograma de seguimiento
- Administración de plantas y áreas
- Exportación Excel
- Exportación PDF

## Nota importante

En el plan gratuito de Render, los archivos JSON y fotos cargadas pueden perderse al redeploy. Para uso real, se recomienda migrar la persistencia a PostgreSQL de Render.
