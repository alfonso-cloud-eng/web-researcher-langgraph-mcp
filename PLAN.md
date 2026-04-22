
# `plan.md`: Deep Research Navigator Agent

## 1. Visión General del Proyecto
**Objetivo:** Construir un agente autónomo de investigación profunda capaz de recibir una URL inicial y una pregunta compleja. El agente navegará la web (usando clics, scrolls, interactuando con menús) mediante un servidor MCP que controla un navegador real (Puppeteer/Playwright), operando bajo un flujo de control cíclico gestionado por LangGraph.

**Stack Tecnológico:**
- **Orquestador:** Python con LangGraph (elegido por su madurez en persistencia de estados complejos y grafos cíclicos).
- **Herramientas (Tooling):** Model Context Protocol (MCP) usando `langchain-mcp`.
- **Navegador:** Servidor MCP en TypeScript con Playwright/Puppeteer.
- **LLM:** Modelos con capacidades avanzadas de razonamiento y uso de herramientas (ej. Claude 3.5 Sonnet o GPT-4o).

---

## 2. Estructura de Archivos Sugerida
El proyecto adopta una arquitectura modular, separando la lógica del grafo, el estado, las herramientas (MCP) y los prompts.

```text
deep-research-navigator/
├── mcp_browser_server/         # Servidor MCP en TypeScript (Playwright)
│   ├── package.json
│   ├── src/
│   │   ├── index.ts            # Registro de herramientas MCP
│   │   └── browser.ts          # Lógica de Playwright (DOM a Markdown, clics)
├── agent/                      # Cliente LangGraph en Python
│   ├── main.py                 # Entrypoint (CLI o API)
│   ├── state.py                # Definición del TypedDict del State
│   ├── graph.py                # Definición de Nodos y Aristas (LangGraph)
│   ├── mcp_client.py           # Conexión asíncrona al servidor MCP
│   ├── prompts.py              # Plantillas de prompts para los nodos
│   └── nodes/                  # Lógica aislada de cada nodo
│       ├── analyst.py
│       ├── navigator.py
│       ├── extractor.py
│       └── verifier.py
├── .env
├── requirements.txt
└── plan.md                     # Este archivo
```

---

## 3. Definición del Estado (State)
El estado persistirá en cada paso del grafo. Usaremos `TypedDict` en Python (`agent/state.py`).

```python
from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    # Inputs iniciales
    question: str
    initial_url: str
    
    # Navegación y Memoria
    current_url: str
    visited_urls: List[str]
    history: List[BaseMessage]        # Historial de conversación/tool calls para el LLM
    reasoning_steps: List[str]        # Cadena de pensamientos explícita del agente
    
    # Estado del DOM actual
    page_content_markdown: str        # HTML limpio y convertido a Markdown
    interactive_elements: Dict[int, Dict[str, Any]] # Mapa de IDs a elementos {1: {"type": "link", "text": "Login", "selector": "..."}}
    current_screenshot: Optional[str] # Screenshot en Base64 (opcional, para modelos multimodales)
    
    # Resultados y Control
    proposed_answer: Optional[str]
    final_answer: Optional[str]
    error_log: Optional[str]
    loop_count: int                   # Para evitar bucles infinitos
```

---

## 4. Arquitectura del Grafo (Nodos y Aristas)

### 4.1. Nodos
1. **Extractor:** 
   - Llama a la herramienta MCP `get_dom_state`. 
   - Recibe el DOM limpio en Markdown, un diccionario de elementos interactivos numerados (ej. `[1] Click here`), y un screenshot. 
   - Actualiza `page_content_markdown` e `interactive_elements` en el estado.
2. **Analyst (El Cerebro):** 
   - Recibe la `question`, el Markdown actual y el historial.
   - Reflexiona sobre qué hacer a continuación.
   - Decide una de tres salidas: `ACT` (Llamar a una herramienta de navegación), `ANSWER` (Ha encontrado la respuesta), o `GIVE_UP` (Límite alcanzado o sin salidas).
3. **Navigator:** 
   - Ejecuta la acción decidida por el Analyst llamando al servidor MCP (ej. `click(element_id=5)`, `scroll()`, `type(element_id=2, text="query")`).
   - Actualiza `current_url` y `visited_urls`. Maneja errores de navegación (ej. "Elemento no encontrado").
4. **Verifier:** 
   - Evalúa críticamente la `proposed_answer` del Analyst contra la `question` original y los hechos recopilados.
   - Si es correcta y completa, establece `final_answer`. Si no, genera un feedback y devuelve el control al Analyst.

### 4.2. Aristas (Control de Flujo)
- `START` -> `Extractor`
- `Extractor` -> `Analyst`
- `Analyst` -> (Conditional Edge):
  - Si acción es navegar -> `Navigator`
  - Si propone respuesta -> `Verifier`
  - Si se rinde/falla -> `END`
- `Navigator` -> `Extractor` *(Cierra el bucle principal de navegación)*
- `Verifier` -> (Conditional Edge):
  - Si verificación exitosa -> `END`
  - Si verificación falla -> `Analyst` *(Para que intente otra ruta)*

---

## 5. Configuración del Servidor MCP y Herramientas

El servidor MCP (escrito en TypeScript para aprovechar Playwright) expondrá las siguientes herramientas al agente:

* **`goto(url)`**: Carga una URL.
* **`get_page_context()`**: 
  - **Core Logic:** Inyecta un script en el navegador que asigna un `data-playwright-id` numérico a cada elemento interactivo (`a`, `button`, `input`).
  - Devuelve: Un objeto JSON con el texto de la página en Markdown (donde los enlaces se muestran como `[Texto del enlace](ID: 5)`) y un mapa numérico de selectores.
* **`click_element(id)`**: Usa el mapa generado para hacer clic en el elemento correspondiente. Espera a que la red se estabilice.
* **`type_text(id, text)`**: Escribe texto en un input específico.
* **`scroll_down()` / `scroll_up()`**: Hace scroll de una ventana gráfica (viewport).
* **`take_screenshot()`**: Devuelve la pantalla en Base64.

*Nota de integración Python:* Usa `mcp.client.stdio` para iniciar el servidor de Playwright como un subproceso y vincular dinámicamente estas herramientas a LangChain usando `bind_tools()`.

---

## 6. Lógica de Navegación "Humana" (Analyst Prompt)

El nodo Analyst debe usar **Information Foraging Theory** (buscar el "olor" de la información).

**Ejemplo de Prompt del Sistema:**
> "Eres un investigador experto. Tu objetivo es responder: '{question}'.
> Estás en la página: '{current_url}'.
> Tienes un límite de {max_loops} pasos (actual: {loop_count}).
> Lee el contenido en Markdown a continuación. Los elementos interactivos están marcados con un ID numérico, ej: `[Siguiente página](ID: 12)`.
> 
> Antes de actuar, debes estructurar tu respuesta de la siguiente manera:
> 1. **Observación**: ¿Qué información útil hay en la pantalla actual?
> 2. **Evaluación**: ¿Esta página contiene la respuesta completa a la pregunta?
> 3. **Planificación**: Si no, ¿qué enlace o acción tiene la mayor probabilidad de acercarme a la respuesta?
> 4. **Acción**: Invoca la herramienta correspondiente (`click_element`, `scroll`, o `submit_answer`)."

**Ejemplo del "Pensamiento" del Agente (Generación esperada):**
```json
{
  "thought_process": {
    "observation": "Estoy en la página de inicio del repositorio de la empresa. Veo un menú de navegación principal con enlaces a 'Docs (ID: 3)', 'Blog (ID: 4)' y 'About (ID: 5)'. La pregunta pide detalles técnicos sobre la API v2.",
    "evaluation": "La página de inicio no contiene los detalles técnicos de la API.",
    "planning": "El enlace 'Docs' (ID: 3) es el camino más lógico para encontrar documentación de APIs. Debo hacer clic ahí.",
    "action_intent": "click_element(3)"
  }
}
```

---

## 7. Guía de Implementación Paso a Paso

### Paso 1: Setup del Entorno y MCP
1. Inicializar el proyecto `mcp_browser_server` con `npm init`.
2. Instalar dependencias de MCP SDK (`@modelcontextprotocol/sdk`) y `playwright`.
3. Implementar `get_page_context` en Playwright. Un buen enfoque es inyectar un JS que recorra el DOM, asigne IDs y extraiga innerText limpio.
4. Inicializar entorno Python, instalar `langgraph`, `langchain`, `langchain-mcp`, `pydantic`.

### Paso 2: Conexión MCP - Python
1. Escribir `mcp_client.py` en Python que arranque el servidor Node como un subproceso STDIO.
2. Recuperar la lista de herramientas del servidor MCP y convertirlas a herramientas compatibles con Langchain (`tool_wrapper`).

### Paso 3: Definición de LangGraph
1. Crear `state.py` definiendo el estado (ver sección 3).
2. Crear `nodes/` implementando cada nodo. 
   - El `Extractor` llamará a `get_page_context`.
   - El `Analyst` usará un LLM con `bind_tools` atado a las herramientas MCP y a una herramienta local `submit_answer`.
3. Crear `graph.py` ensamblando el `StateGraph`, añadiendo Checkpointers (MemorySaver) para persistencia de LangGraph.

### Paso 4: Prompt Engineering
1. Refinar `prompts.py` asegurando que el LLM reciba el contexto formateado de manera que entienda los IDs numéricos, ya que los LLMs fallan frecuentemente si se les pide escribir XPath o selectores CSS complejos. El enfoque de IDs numéricos es vital.

### Paso 5: Manejo de Errores y Edge Cases
1. **Páginas que no cargan o Timeout:** El `Navigator` debe atrapar excepciones de Playwright. Si falla, el estado se actualiza con `error_log="Timeout cargando la página"`. El `Extractor` pasa ese error al `Analyst`, quien decide hacer click en el botón de retroceso (`go_back`) o probar otro enlace.
2. **Modales de Cookies/Popups:** Añadir lógica genérica en el `Extractor` que, si detecta botones con texto "Aceptar todas" o "Cerrar", sugiera fuertemente al `Analyst` cerrarlos primero para limpiar el DOM.
3. **Infinite Loops:** En `graph.py`, añadir una arista condicional global: si `state["loop_count"] > 20`, forzar transición al nodo `END` con el estado de fallo.

### Paso 6: Testing
1. Probar con una URL inicial fácil (ej. Wikipedia) y una pregunta simple.
2. Rastrear visualmente la ejecución de Playwright (habilitando `headless: false` temporalmente en el servidor MCP) para ver los clics fantasmas del agente.