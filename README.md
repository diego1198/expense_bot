<div align="center">

# 💰 Bot de Gastos Personales

### Tu asistente inteligente para controlar tus finanzas personales

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app)

[🚀 Comenzar](#-instalación-rápida) · [📖 Documentación](#-uso) · [💡 Características](#-características)

---

</div>

## ✨ ¿Qué hace este bot?

Registra tus gastos de forma **natural** — solo escribe o habla. La IA se encarga del resto.

```
Tú: "Gasté 25 dólares en almuerzo"
Bot: ✅ Gasto registrado: $25.00 USD - Almuerzo (🍔 Alimentación)
```

<div align="center">

| 💬 Escribe natural | 🎤 Envía audios | 📧 Detecta facturas |
|:---:|:---:|:---:|
| "uber 8.50" | 🗣️ "Pagué 50 en gasolina" | PDFs del correo → gastos |

</div>

---

## 🎯 Características

<table>
<tr>
<td width="50%">

### 📝 Registro Inteligente
- **Texto natural** — Escribe como hablas
- **Voz a texto** — Envía audios (Whisper)
- **Clasificación IA** — Categoriza automáticamente
- **Método de pago** — Efectivo, tarjeta o transferencia

</td>
<td width="50%">

### 📧 Integración Email
- **Gmail IMAP** — Conecta tu correo
- **Lectura de PDFs** — Extrae datos de facturas
- **Auto-detección** — Escaneo periódico
- **Facturas SRI** — Soporte Ecuador 🇪🇨

</td>
</tr>
<tr>
<td width="50%">

### 📊 Estadísticas
- **Resumen mensual** — Total y promedio diario
- **Resumen anual** — Tendencias de gasto
- **Por categoría** — Distribución visual
- **Historial** — Consulta gastos anteriores

</td>
<td width="50%">

### 🎛️ Interfaz Amigable
- **Botones interactivos** — Sin memorizar comandos
- **Comandos en español** — `/ver_gastos`, `/estadisticas`
- **Confirmaciones** — Verifica antes de guardar
- **Menú rápido** — Acceso a todo con `/menu`

</td>
</tr>
</table>

---

## 🚀 Instalación Rápida

### Prerrequisitos

- Python 3.11+
- [Token de Telegram Bot](https://t.me/BotFather)
- [API Key de OpenAI](https://platform.openai.com/api-keys)

### 1️⃣ Clonar e instalar

```bash
git clone https://github.com/tu-usuario/bot-gastos-personales.git
cd bot-gastos-personales

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2️⃣ Configurar

```bash
cp .env.example .env
```

Edita `.env`:

```env
TELEGRAM_BOT_TOKEN=tu_token_aquí
OPENAI_API_KEY=sk-...
ALLOWED_USER_IDS=tu_telegram_id    # Opcional
DEFAULT_CURRENCY=USD
TIMEZONE=America/Guayaquil
```

### 3️⃣ Ejecutar

```bash
python -m src.main
```

✅ ¡Listo! Busca tu bot en Telegram y envía `/start`

---

## 📖 Uso

### Comandos Principales

| Comando | Descripción |
|:--------|:------------|
| `/menu` | 📱 Menú interactivo con botones |
| `/estadisticas` | 📊 Resumen del mes |
| `/ver_gastos` | 📋 Últimos 10 gastos |
| `/buscar_facturas` | 📧 Buscar en tu correo |
| `/ayuda` | ❓ Instrucciones de uso |

### Ejemplos de Registro

Solo escribe o envía un audio:

```
✅ 11.40 desayuno
✅ Uber a la oficina $8.50
✅ Netflix 15.99
✅ Pagué la luz, 45 dólares
✅ Súper mercado 120
```

### Categorías

| | | | | |
|:---:|:---:|:---:|:---:|:---:|
| 🍔 Alimentación | 🚗 Transporte | 🏠 Hogar | 🛒 Compras | 💊 Salud |
| 🎬 Entretenimiento | 📚 Educación | 💼 Trabajo | 🐕 Mascotas | 🎁 Otros |

---

## 📧 Integración con Gmail

Detecta automáticamente facturas en tu correo y extrae los datos de PDFs adjuntos.

```bash
/conectar_email tu@gmail.com tu_contraseña_de_aplicación
```

> 💡 Necesitas una [contraseña de aplicación](https://myaccount.google.com/apppasswords), no tu contraseña normal.

**Detecta automáticamente:**
- ✅ Facturas electrónicas (SRI Ecuador)
- ✅ Recibos de compra
- ✅ Confirmaciones de pago
- ✅ PDFs adjuntos con montos

---

## 🚂 Deploy en Railway

El proyecto está listo para deploy en Railway:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

### Pasos:

1. Conecta tu repo de GitHub a Railway
2. Agrega las variables de entorno
3. Añade un Volume en `/data` (persistencia)
4. ¡Deploy automático! 🎉

---

## 🏗️ Arquitectura

```
bot-gastos-personales/
├── src/
│   ├── main.py                  # Punto de entrada
│   ├── config.py                # Configuración
│   ├── bot/handlers.py          # Comandos de Telegram
│   ├── database/
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── connection.py        # Conexión async
│   │   └── repository.py        # CRUD operations
│   ├── services/
│   │   ├── expense_parser.py    # Parser con GPT
│   │   ├── email_parser.py      # Parser de emails/PDFs
│   │   ├── gmail_service.py     # IMAP service
│   │   └── voice_transcriber.py # Whisper API
│   └── analytics/               # Estadísticas
├── data/                        # SQLite database
├── requirements.txt
├── Procfile                     # Railway
└── railway.toml
```

---

## 💰 Costos Estimados

| Servicio | Mensual |
|:---------|--------:|
| Telegram Bot API | **Gratis** |
| OpenAI GPT-4o-mini | ~$0.50-2.00 |
| OpenAI Whisper | ~$0.10-0.50 |
| Railway | ~$5.00 |
| **Total** | **~$5-8** |

---

## 🛠️ Tech Stack

<div align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/python--telegram--bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=openai&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white)

</div>

- **python-telegram-bot** — Framework async para Telegram
- **OpenAI GPT-4o-mini** — Clasificación inteligente de gastos
- **OpenAI Whisper** — Transcripción de voz
- **SQLAlchemy 2.0** — ORM async con aiosqlite
- **pdfplumber** — Extracción de texto de PDFs
- **pytz** — Manejo de zonas horarias

---

## 📄 Licencia

MIT © 2025

---

<div align="center">

**¿Te gustó el proyecto?** ⭐ Dale una estrella

[Reportar Bug](../../issues) · [Solicitar Feature](../../issues)

</div>
