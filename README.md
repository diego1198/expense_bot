# Bot de Gastos Personales 💰

Bot de Telegram para registrar y analizar tus gastos personales usando inteligencia artificial.

## Características

- 📝 **Registro de gastos por texto**: Escribe naturalmente "Gasté 150 en uber"
- 🎤 **Registro por voz**: Envía un mensaje de voz describiendo tu gasto
- 🤖 **IA para clasificación**: GPT-4o-mini clasifica automáticamente tus gastos
- 📊 **Estadísticas**: Reportes mensuales y anuales con gráficos
- ✅ **Confirmación**: Cada gasto requiere tu confirmación antes de guardarse
- 📂 **Categorías**: 9 categorías predefinidas (personalizables)

## Requisitos

- Python 3.11+
- Token de Bot de Telegram (de @BotFather)
- API Key de OpenAI

## Instalación

### 1. Clonar y configurar entorno

```bash
cd bot-gastos-personales

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar con tus credenciales
nano .env  # o usa tu editor preferido
```

Configura estas variables en `.env`:

```env
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
OPENAI_API_KEY=tu_api_key_de_openai
ALLOWED_USER_IDS=tu_telegram_user_id  # Opcional, para restringir acceso
```

### 3. Obtener credenciales

#### Token de Telegram Bot
1. Abre Telegram y busca @BotFather
2. Envía `/newbot` y sigue las instrucciones
3. Copia el token que te proporciona

#### API Key de OpenAI
1. Ve a https://platform.openai.com/api-keys
2. Crea una nueva API key
3. Copia la key

#### Tu Telegram User ID (opcional)
1. Busca @userinfobot en Telegram
2. Te enviará tu ID de usuario

### 4. Ejecutar el bot

```bash
python -m src.main
```

## Uso

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `/start` | Iniciar el bot |
| `/help` | Ver ayuda |
| `/stats` | Estadísticas del mes actual |
| `/stats_year` | Estadísticas del año |
| `/categories` | Ver categorías disponibles |
| `/history` | Ver últimos 10 gastos |

### Ejemplos de registro

```
Gasté 150 en uber
500 pesos en supermercado
Netflix 199
$200 café starbucks
Pagué la luz, 800 pesos
```

### Categorías predefinidas

- 🍔 Alimentación
- 🚗 Transporte  
- 🏠 Hogar
- 🛒 Compras
- 💊 Salud
- 🎬 Entretenimiento
- 📚 Educación
- 💼 Trabajo
- 🎁 Otros

## Estructura del proyecto

```
bot-gastos-personales/
├── src/
│   ├── __init__.py
│   ├── main.py              # Punto de entrada
│   ├── config.py            # Configuración
│   ├── bot/
│   │   ├── __init__.py
│   │   └── handlers.py      # Handlers de Telegram
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py        # Modelos SQLAlchemy
│   │   ├── connection.py    # Conexión a BD
│   │   └── repository.py    # Operaciones CRUD
│   ├── services/
│   │   ├── __init__.py
│   │   ├── expense_parser.py    # Parser con GPT
│   │   └── voice_transcriber.py # Transcripción de voz
│   └── analytics/
│       └── __init__.py      # Estadísticas y gráficos
├── data/                    # Base de datos SQLite
├── .env                     # Variables de entorno
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Despliegue en producción

### Opción 1: Railway ($3-5/mes)

```bash
# Instalar Railway CLI
npm install -g @railway/cli

# Login y deploy
railway login
railway init
railway up
```

### Opción 2: Fly.io ($3-5/mes)

```bash
# Instalar flyctl
brew install flyctl  # macOS

# Deploy
fly launch
fly deploy
```

### Opción 3: Docker

```bash
docker build -t expense-bot .
docker run -d --env-file .env expense-bot
```

## Costos estimados

| Servicio | Costo mensual |
|----------|---------------|
| Telegram Bot API | Gratis |
| OpenAI GPT-4o-mini | ~$0.30-2.00 |
| OpenAI Whisper | ~$0.10-0.50 |
| Hosting | $0-5.00 |
| **Total** | **~$1-8/mes** |

## Próximas funciones

- [ ] Integración con Gmail para detectar facturas
- [ ] Soporte para WhatsApp
- [ ] Exportar datos a CSV/Excel
- [ ] Gráficos avanzados
- [ ] Presupuestos y alertas
- [ ] Multi-moneda con conversión

## Licencia

MIT
