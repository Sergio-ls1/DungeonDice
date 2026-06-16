"""
sanctuary.py  –  Santuarios del Conocimiento

Módulo independiente. No toca combate, cartas, dados, turnos ni guardado.

Exporta:
    SanctuaryMinigame   – clase que gestiona el minijuego de preguntas.
    SANCTUARY_POSITIONS – coordenadas (tile_x, tile_y) de los santuarios en el mapa.
"""

import pygame
import os
import random
import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Assets / fonts
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[2]

def resource_path(relative_path):
    import sys
    
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
        
    p = Path(relative_path)
    if p.is_absolute():
        try:
            file_path = Path(__file__).resolve()
            if "engine" in file_path.parts:
                root_path = file_path.parents[2]
            elif "network" in file_path.parts:
                root_path = file_path.parents[2]
            else:
                root_path = file_path.parents[1]
            p = p.relative_to(root_path)
        except Exception:
            pass
    return os.path.join(base_path, str(p))


def _get_font(size: int) -> pygame.font.Font:
    fp = BASE / "assets" / "fonts" / "pixel.ttf"
    res_fp = resource_path(fp)
    if os.path.exists(res_fp):
        return pygame.font.Font(res_fp, size)
    return pygame.font.SysFont("courier", size, bold=True)


# ---------------------------------------------------------------------------
# Posiciones de santuarios en el mapa (tile_x, tile_y)
# ---------------------------------------------------------------------------
SANCTUARY_POSITIONS = [
    (12, 10),
    (38,  8),
    (20, 24),
    (42, 22),
    ( 8, 20),
    (30,  6),
    (45, 26),
]


# ---------------------------------------------------------------------------
# Banco de 40 preguntas – organizado por tema
#
# Temas cubiertos (2 preguntas cada uno):
#   Windows | Linux | macOS | BIOS | Drivers | ASCII | Hardware | Software |
#   CPU | RAM | Placa Madre | Bus de Datos | Digitalización | Audio Digital |
#   Video Digital | Imagen Digital | Texto Digital | HDD | SSD | USB |
#   Periféricos de Entrada | Periféricos de Salida
#
# Formato:
#   "topic"   – nombre del tema (referencial)
#   "q"       – enunciado de la pregunta
#   "opts"    – lista de 4 opciones; la PRIMERA (índice 0) es la correcta
#   "correct" – siempre 0 (las opciones se barajan al mostrar)
# ---------------------------------------------------------------------------
QUESTION_BANK = [

    # ── WINDOWS (2) ───────────────────────────────────────────────────────
    {
        "topic": "Windows",
        "q": "¿Qué empresa desarrolló el sistema operativo Windows?",
        "opts": [
            "Microsoft",
            "Apple",
            "Google",
            "IBM",
        ],
        "correct": 0,
    },
    {
        "topic": "Windows",
        "q": "¿Cuál es la versión más reciente de Windows (2024)?",
        "opts": [
            "Windows 11",
            "Windows 10",
            "Windows 8",
            "Windows Vista",
        ],
        "correct": 0,
    },

    # ── LINUX (2) ─────────────────────────────────────────────────────────
    {
        "topic": "Linux",
        "q": "¿Qué tipo de software es Linux?",
        "opts": [
            "Sistema operativo de código abierto",
            "Navegador web de pago",
            "Antivirus propietario",
            "Procesador de texto",
        ],
        "correct": 0,
    },
    {
        "topic": "Linux",
        "q": "¿Cuál de estas es una distribución de Linux?",
        "opts": [
            "Ubuntu",
            "macOS",
            "Windows XP",
            "Chrome",
        ],
        "correct": 0,
    },

    # ── macOS (2) ─────────────────────────────────────────────────────────
    {
        "topic": "macOS",
        "q": "¿Qué empresa desarrolla el sistema operativo macOS?",
        "opts": [
            "Apple",
            "Microsoft",
            "Intel",
            "Samsung",
        ],
        "correct": 0,
    },
    {
        "topic": "macOS",
        "q": "¿En qué hardware está diseñado principalmente macOS?",
        "opts": [
            "Computadoras Mac de Apple",
            "Cualquier PC genérico",
            "Servidores Linux",
            "Teléfonos Android",
        ],
        "correct": 0,
    },

    # ── BIOS (2) ──────────────────────────────────────────────────────────
    {
        "topic": "BIOS",
        "q": "¿Qué significa la sigla BIOS?",
        "opts": [
            "Basic Input Output System",
            "Binary Internal Operating Software",
            "Boot Interface Output System",
            "Basic Internet Operating Setup",
        ],
        "correct": 0,
    },
    {
        "topic": "BIOS",
        "q": "¿Cuál es la función principal del BIOS al encender el computador?",
        "opts": [
            "Inicializar el hardware y arrancar el sistema operativo",
            "Guardar archivos del usuario",
            "Conectarse a internet automáticamente",
            "Reproducir sonidos de inicio",
        ],
        "correct": 0,
    },

    # ── DRIVERS (2) ───────────────────────────────────────────────────────
    {
        "topic": "Drivers",
        "q": "¿Qué es un driver (controlador de dispositivo)?",
        "opts": [
            "Software que permite al SO comunicarse con el hardware",
            "Un tipo de virus informático",
            "Un disco duro externo",
            "Una versión de Windows",
        ],
        "correct": 0,
    },
    {
        "topic": "Drivers",
        "q": "¿Qué ocurre si una impresora no tiene su driver instalado?",
        "opts": [
            "El sistema operativo no puede controlarla",
            "La impresora imprime solo en blanco y negro",
            "La impresora trabaja más rápido",
            "No ocurre ningún cambio",
        ],
        "correct": 0,
    },

    # ── ASCII (2) ─────────────────────────────────────────────────────────
    {
        "topic": "ASCII",
        "q": "¿Qué significa la sigla ASCII?",
        "opts": [
            "American Standard Code for Information Interchange",
            "Automatic System Code for Internet Interface",
            "Advanced Standard Computer Input Interface",
            "American Software Control Information Index",
        ],
        "correct": 0,
    },
    {
        "topic": "ASCII",
        "q": "¿Cuántos bits utiliza el código ASCII estándar (original)?",
        "opts": [
            "7 bits",
            "8 bits",
            "16 bits",
            "32 bits",
        ],
        "correct": 0,
    },

    # ── HARDWARE (2) ──────────────────────────────────────────────────────
    {
        "topic": "Hardware",
        "q": "¿Qué se entiende por hardware de un computador?",
        "opts": [
            "Los componentes físicos y tangibles del equipo",
            "Los programas e instrucciones digitales",
            "Los archivos guardados en el disco",
            "El sistema operativo instalado",
        ],
        "correct": 0,
    },
    {
        "topic": "Hardware",
        "q": "¿Cuál de los siguientes elementos es hardware?",
        "opts": [
            "Tarjeta gráfica",
            "Microsoft Word",
            "Sistema operativo Linux",
            "Archivo PDF",
        ],
        "correct": 0,
    },

    # ── SOFTWARE (2) ──────────────────────────────────────────────────────
    {
        "topic": "Software",
        "q": "¿Qué es el software de un computador?",
        "opts": [
            "Conjunto de programas, instrucciones y datos",
            "Los cables y circuitos del equipo",
            "La fuente de alimentación eléctrica",
            "La pantalla del monitor",
        ],
        "correct": 0,
    },
    {
        "topic": "Software",
        "q": "¿Cuál de estos es un ejemplo de software de aplicación?",
        "opts": [
            "Microsoft Excel",
            "Placa madre",
            "Memoria RAM",
            "Disco duro SSD",
        ],
        "correct": 0,
    },

    # ── CPU (2) ───────────────────────────────────────────────────────────
    {
        "topic": "CPU",
        "q": "¿Qué significa la sigla CPU?",
        "opts": [
            "Central Processing Unit",
            "Central Program Utility",
            "Computer Processor Unit",
            "Core Power Unit",
        ],
        "correct": 0,
    },
    {
        "topic": "CPU",
        "q": "¿Cuál es la función principal de la CPU?",
        "opts": [
            "Ejecutar y procesar instrucciones del programa",
            "Almacenar datos de forma permanente",
            "Mostrar imágenes en la pantalla",
            "Conectar periféricos por USB",
        ],
        "correct": 0,
    },

    # ── RAM (2) ───────────────────────────────────────────────────────────
    {
        "topic": "RAM",
        "q": "¿Qué significa la sigla RAM?",
        "opts": [
            "Random Access Memory",
            "Read Access Module",
            "Rapid Allocation Memory",
            "Remote Access Memory",
        ],
        "correct": 0,
    },
    {
        "topic": "RAM",
        "q": "¿Qué característica define a la memoria RAM?",
        "opts": [
            "Es volátil: pierde datos al apagar el equipo",
            "Guarda datos de forma permanente",
            "Funciona sin electricidad",
            "Es un tipo de disco duro",
        ],
        "correct": 0,
    },

    # ── PLACA MADRE (2) ───────────────────────────────────────────────────
    {
        "topic": "Placa Madre",
        "q": "¿Qué es la placa madre (motherboard)?",
        "opts": [
            "Circuito principal que interconecta todos los componentes del PC",
            "Un tipo de memoria RAM de alta velocidad",
            "El procesador central del equipo",
            "La tarjeta que controla el audio",
        ],
        "correct": 0,
    },
    {
        "topic": "Placa Madre",
        "q": "¿Cuáles componentes se conectan directamente a la placa madre?",
        "opts": [
            "CPU, RAM y tarjetas de expansión",
            "Solo el monitor y el teclado",
            "Únicamente los discos duros",
            "Solo la fuente de poder",
        ],
        "correct": 0,
    },

    # ── BUS DE DATOS (2) ──────────────────────────────────────────────────
    {
        "topic": "Bus de Datos",
        "q": "¿Qué es un bus de datos en un computador?",
        "opts": [
            "Conjunto de líneas que transfieren datos entre componentes",
            "Un programa que organiza archivos",
            "El cable que conecta el monitor al CPU",
            "Una unidad de almacenamiento secundario",
        ],
        "correct": 0,
    },
    {
        "topic": "Bus de Datos",
        "q": "¿Cuántos bits transfiere simultáneamente un bus de 32 bits?",
        "opts": [
            "32 bits a la vez",
            "8 bits a la vez",
            "64 bits a la vez",
            "16 bits a la vez",
        ],
        "correct": 0,
    },

    # ── DIGITALIZACIÓN (2) ────────────────────────────────────────────────
    {
        "topic": "Digitalización",
        "q": "¿Qué significa digitalizar información?",
        "opts": [
            "Convertir información analógica en datos binarios (0 y 1)",
            "Imprimir documentos en papel",
            "Conectar dispositivos por cable",
            "Guardar archivos en la nube",
        ],
        "correct": 0,
    },
    {
        "topic": "Digitalización",
        "q": "¿Cuáles son los dos pasos principales para digitalizar audio?",
        "opts": [
            "Muestreo y cuantización",
            "Compresión y cifrado",
            "Impresión y escaneo",
            "Formateo y partición",
        ],
        "correct": 0,
    },

    # ── AUDIO DIGITAL (2) ─────────────────────────────────────────────────
    {
        "topic": "Audio Digital",
        "q": "¿Qué es la frecuencia de muestreo en audio digital?",
        "opts": [
            "Cantidad de muestras tomadas por segundo de la señal de audio",
            "El volumen máximo del parlante",
            "La calidad del micrófono",
            "El tamaño del archivo de música",
        ],
        "correct": 0,
    },
    {
        "topic": "Audio Digital",
        "q": "¿Cuál es la frecuencia de muestreo estándar para CD de audio?",
        "opts": [
            "44,100 Hz",
            "8,000 Hz",
            "96,000 Hz",
            "22,050 Hz",
        ],
        "correct": 0,
    },

    # ── VIDEO DIGITAL (2) ─────────────────────────────────────────────────
    {
        "topic": "Video Digital",
        "q": "¿Cómo está compuesto el video digital?",
        "opts": [
            "Una secuencia de imágenes (fotogramas) mostradas por segundo",
            "Una señal de audio continua",
            "Un archivo de texto con instrucciones",
            "Una serie de frecuencias de radio",
        ],
        "correct": 0,
    },
    {
        "topic": "Video Digital",
        "q": "¿Qué significa la abreviación FPS en video digital?",
        "opts": [
            "Frames Per Second (fotogramas por segundo)",
            "File Processing System",
            "Fast Pixel Scanning",
            "Frequency Phase Signal",
        ],
        "correct": 0,
    },

    # ── IMAGEN DIGITAL (2) ────────────────────────────────────────────────
    {
        "topic": "Imagen Digital",
        "q": "¿Qué es un píxel en una imagen digital?",
        "opts": [
            "La unidad mínima de color e información de una imagen",
            "El tamaño total de la imagen en megabytes",
            "El número de colores del monitor",
            "La velocidad de refresco de la pantalla",
        ],
        "correct": 0,
    },
    {
        "topic": "Imagen Digital",
        "q": "¿Qué indica la resolución de una imagen (ej. 1920×1080)?",
        "opts": [
            "Cantidad de píxeles de ancho por alto",
            "El tamaño físico en centímetros",
            "La cantidad de colores disponibles",
            "El peso del archivo en kilobytes",
        ],
        "correct": 0,
    },

    # ── TEXTO DIGITAL (2) ─────────────────────────────────────────────────
    {
        "topic": "Texto Digital",
        "q": "¿Cómo se representa un carácter de texto en el computador?",
        "opts": [
            "Mediante un código numérico binario (como ASCII o Unicode)",
            "Con una fotografía de la letra",
            "Como una señal de radio",
            "Con un dibujo vectorial",
        ],
        "correct": 0,
    },
    {
        "topic": "Texto Digital",
        "q": "¿Qué estándar amplió ASCII para incluir más idiomas y símbolos?",
        "opts": [
            "Unicode (UTF-8)",
            "BIOS-16",
            "HTML básico",
            "ASCII extendido v2",
        ],
        "correct": 0,
    },

    # ── HDD (2) ───────────────────────────────────────────────────────────
    {
        "topic": "HDD",
        "q": "¿Qué significa la sigla HDD?",
        "opts": [
            "Hard Disk Drive",
            "High Data Device",
            "Hardware Digital Disk",
            "Hybrid Data Drive",
        ],
        "correct": 0,
    },
    {
        "topic": "HDD",
        "q": "¿Cómo almacena los datos un disco duro HDD?",
        "opts": [
            "En platos magnéticos giratorios leídos por un cabezal",
            "En chips de memoria flash sin partes móviles",
            "En cintas de fibra óptica",
            "En circuitos integrados de silicio",
        ],
        "correct": 0,
    },

    # ── SSD (2) ───────────────────────────────────────────────────────────
    {
        "topic": "SSD",
        "q": "¿Qué significa la sigla SSD?",
        "opts": [
            "Solid State Drive",
            "System Storage Device",
            "Secondary Software Disk",
            "Super Speed Data",
        ],
        "correct": 0,
    },
    {
        "topic": "SSD",
        "q": "¿Cuál es la principal ventaja del SSD frente al HDD?",
        "opts": [
            "Mayor velocidad de lectura/escritura y sin partes móviles",
            "Mayor capacidad de almacenamiento a menor costo",
            "Funciona sin electricidad",
            "Puede almacenarse bajo el agua",
        ],
        "correct": 0,
    },

    # ── USB (2) ───────────────────────────────────────────────────────────
    {
        "topic": "USB",
        "q": "¿Qué significa la sigla USB?",
        "opts": [
            "Universal Serial Bus",
            "Unified System Board",
            "Universal Software Base",
            "User Storage Base",
        ],
        "correct": 0,
    },
    {
        "topic": "USB",
        "q": "¿Para qué se usa principalmente una memoria USB?",
        "opts": [
            "Almacenar y transportar datos entre equipos",
            "Acelerar el procesador del PC",
            "Aumentar la memoria RAM",
            "Conectar el monitor al PC",
        ],
        "correct": 0,
    },

    # ── PERIFÉRICOS DE ENTRADA (2) ────────────────────────────────────────
    {
        "topic": "Periféricos de Entrada",
        "q": "¿Cuál de los siguientes es un periférico de entrada?",
        "opts": [
            "Teclado",
            "Monitor",
            "Parlante",
            "Impresora",
        ],
        "correct": 0,
    },
    {
        "topic": "Periféricos de Entrada",
        "q": "¿Por qué el escáner se clasifica como periférico de entrada?",
        "opts": [
            "Porque envía datos (imagen digitalizada) al computador",
            "Porque muestra información al usuario",
            "Porque almacena datos permanentemente",
            "Porque procesa instrucciones del SO",
        ],
        "correct": 0,
    },

    # ── PERIFÉRICOS DE SALIDA (2) ─────────────────────────────────────────
    {
        "topic": "Periféricos de Salida",
        "q": "¿Cuál de los siguientes es un periférico de salida?",
        "opts": [
            "Monitor",
            "Mouse",
            "Micrófono",
            "Cámara web",
        ],
        "correct": 0,
    },
    {
        "topic": "Periféricos de Salida",
        "q": "¿Por qué los parlantes se clasifican como periféricos de salida?",
        "opts": [
            "Porque emiten información (audio) desde el computador hacia el usuario",
            "Porque capturan el sonido del ambiente",
            "Porque almacenan archivos de música",
            "Porque procesan señales digitales internamente",
        ],
        "correct": 0,
    },

]  # Total: 40 preguntas  |  22 temas  |  2 preguntas por tema


# ---------------------------------------------------------------------------
# Posibles recompensas
# ---------------------------------------------------------------------------
REWARDS = [
    {"label": "+10 HP Máximo",    "type": "max_hp",  "value": 10},
    {"label": "+20 HP Máximo",    "type": "max_hp",  "value": 20},
    {"label": "+5 Escudo",        "type": "shield",  "value": 5},
    {"label": "+10 Escudo",       "type": "shield",  "value": 10},
    {"label": "+1 Nivel",         "type": "level",   "value": 1},
    {"label": "Curación Completa", "type": "heal",    "value": 0},
]

LETTERS = ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# SanctuaryMinigame
# ---------------------------------------------------------------------------
class SanctuaryMinigame:
    """
    Gestiona el minijuego de preguntas dentro de un santuario.

    Estados internos:
        "QUESTION"  – mostrando una pregunta
        "FEEDBACK"  – mostrando si fue correcta/incorrecta (brevemente)
        "REWARD"    – mostrando la recompensa obtenida (3/3 correctas)
        "FAIL"      – mostrando mensaje de fallo
        "DONE"      – terminado, el llamador debe cerrar el minijuego
    """

    QUESTIONS_PER_SESSION = 3

    def __init__(self, hero):
        self.hero       = hero
        self.state      = "QUESTION"
        self.anim_timer = 0.0

        # Fuentes
        self.font_title = _get_font(22)
        self.font_body  = _get_font(16)
        self.font_small = _get_font(13)
        self.font_opt   = _get_font(15)

        # Seleccionar 3 preguntas sin repetir y barajar sus opciones
        chosen = random.sample(QUESTION_BANK, self.QUESTIONS_PER_SESSION)
        self.questions = []
        for q in chosen:
            opts       = list(q["opts"])
            correct_t  = opts[q["correct"]]
            random.shuffle(opts)
            new_correct = opts.index(correct_t)
            self.questions.append({
                "topic":   q.get("topic", ""),
                "q":       q["q"],
                "opts":    opts,
                "correct": new_correct,
            })

        self.current_q         = 0
        self.correct_count     = 0
        self.selected          = None
        self.feedback_timer    = 0.0
        self.feedback_correct  = False
        self.reward_data       = None
        self.done              = False

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------
    def update(self, dt: float):
        self.anim_timer += dt
        if self.state == "FEEDBACK":
            self.feedback_timer -= dt
            if self.feedback_timer <= 0:
                self._advance()

    # ------------------------------------------------------------------
    # handle_event
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event):
        if self.state == "QUESTION":
            if event.type == pygame.KEYDOWN:
                key_map = {
                    pygame.K_a: 0, pygame.K_b: 1,
                    pygame.K_c: 2, pygame.K_d: 3,
                    pygame.K_1: 0, pygame.K_2: 1,
                    pygame.K_3: 2, pygame.K_4: 3,
                }
                if event.key in key_map:
                    self._answer(key_map[event.key])

        elif self.state in ("REWARD", "FAIL"):
            if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_KP_ENTER,
                    pygame.K_SPACE, pygame.K_ESCAPE):
                self.done = True

    def handle_mouse(self, pos):
        """Llamar cuando se detecta un click; pos = coordenadas de pantalla lógica."""
        if self.state != "QUESTION":
            return
        for i, rect in enumerate(self._option_rects()):
            if rect.collidepoint(pos):
                self._answer(i)
                break

    # ------------------------------------------------------------------
    # Lógica interna
    # ------------------------------------------------------------------
    def _answer(self, idx: int):
        if self.state != "QUESTION":
            return
        q = self.questions[self.current_q]
        self.selected         = idx
        self.feedback_correct = (idx == q["correct"])
        if self.feedback_correct:
            self.correct_count += 1
            self.hero.add_exp(5)
        self.state          = "FEEDBACK"
        self.feedback_timer = 1.0

    def _advance(self):
        if not self.feedback_correct:
            self.state = "FAIL"
            return
        self.current_q += 1
        if self.current_q >= self.QUESTIONS_PER_SESSION:
            self._grant_reward()
            self.state = "REWARD"
        else:
            self.selected = None
            self.state    = "QUESTION"

    def _grant_reward(self):
        reward = random.choice(REWARDS)
        self.reward_data = reward
        h = self.hero
        if reward["type"] == "max_hp":
            h.max_hp += reward["value"]
            h.hp += reward["value"]
        elif reward["type"] == "shield":
            h.shield = min(h.max_shield, h.shield + reward["value"])
        elif reward["type"] == "level":
            h.hero_level += reward["value"]
            h.level = h.hero_level
            h.max_hp += 10
            h.hp += 10
            h.max_shield += 5
            h.exp_to_next_level = h.hero_level * 100
            h.pending_level_ups.append(h.hero_level)
        elif reward["type"] == "heal":
            h.hp = h.max_hp

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def _option_rects(self):
        """Devuelve los 4 pygame.Rect de las opciones en coordenadas lógicas."""
        rects = []
        base_y = 310
        for i in range(4):
            rects.append(pygame.Rect(172, base_y + i * 56, 476, 46))
        return rects

    # ------------------------------------------------------------------
    # draw
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface):
        # Fondo oscurecido
        dim = pygame.Surface((884, 640), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 175))
        surface.blit(dim, (0, 0))

        # Panel principal
        pw, ph = 560, 520
        px = (884 - pw) // 2
        py = (640 - ph) // 2

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for row in range(ph):
            ratio = row / ph
            r = int(8  + 4  * ratio)
            g = int(5  + 10 * ratio)
            b = int(28 + 20 * ratio)
            pygame.draw.line(panel, (r, g, b, 240), (0, row), (pw, row))
        surface.blit(panel, (px, py))

        # Borde azul
        pygame.draw.rect(surface, (100, 160, 255), (px, py, pw, ph), 2)
        clen = 16
        for cx, cy, ddx, ddy in [
            (px, py, 1, 1), (px+pw-1, py, -1, 1),
            (px, py+ph-1, 1, -1), (px+pw-1, py+ph-1, -1, -1),
        ]:
            pygame.draw.line(surface, (255, 215, 0), (cx, cy), (cx+ddx*clen, cy), 2)
            pygame.draw.line(surface, (255, 215, 0), (cx, cy), (cx, cy+ddy*clen), 2)

        # Título
        title_t = self.font_title.render(
            "Santuario del Conocimiento", True, (130, 200, 255))
        surface.blit(title_t, title_t.get_rect(center=(px + pw // 2, py + 28)))
        pygame.draw.line(surface, (70, 120, 200),
                         (px + 20, py + 50), (px + pw - 20, py + 50), 1)

        # Contador de preguntas
        q_num = min(self.current_q + 1, self.QUESTIONS_PER_SESSION)
        counter_t = self.font_small.render(
            f"Pregunta {q_num} de {self.QUESTIONS_PER_SESSION}",
            True, (160, 160, 220))
        surface.blit(counter_t, (px + pw - counter_t.get_width() - 14, py + 10))

        # Tema de la pregunta actual
        if self.current_q < len(self.questions):
            topic = self.questions[self.current_q].get("topic", "")
            topic_t = self.font_small.render(f"Tema: {topic}", True, (120, 180, 255))
            surface.blit(topic_t, (px + 14, py + 10))

        # Contenido según estado
        if self.state in ("QUESTION", "FEEDBACK"):
            self._draw_question(surface, px, py, pw)
        elif self.state == "REWARD":
            self._draw_reward(surface, px, py, pw, ph)
        elif self.state == "FAIL":
            self._draw_fail(surface, px, py, pw, ph)

    def _draw_question(self, surface, px, py, pw):
        q = self.questions[self.current_q]

        # Enunciado
        lines = self._wrap_text(q["q"], self.font_body, pw - 40)
        ey = py + 68
        for line in lines:
            ts = self.font_body.render(line, True, (230, 220, 255))
            surface.blit(ts, ts.get_rect(centerx=px + pw // 2, y=ey))
            ey += ts.get_height() + 4

        # Opciones
        rects = self._option_rects()
        for i, rect in enumerate(rects):
            is_sel  = (self.selected == i)
            is_corr = (i == q["correct"])

            if self.state == "FEEDBACK":
                if is_corr:
                    bg, border = (20, 100, 40), (80, 220, 100)
                elif is_sel and not is_corr:
                    bg, border = (100, 20, 20), (220, 60, 60)
                else:
                    bg, border = (18, 14, 40), (60, 55, 100)
            else:
                mx, my = pygame.mouse.get_pos()
                hover = rect.collidepoint(mx, my)
                bg     = (40, 30, 90)    if hover else (18, 14, 40)
                border = (140, 110, 255) if hover else (70, 60, 130)

            pygame.draw.rect(surface, bg, rect, border_radius=6)
            pygame.draw.rect(surface, border, rect, 1, border_radius=6)

            letter_t = self.font_opt.render(
                LETTERS[i] + ")", True, (200, 180, 255))
            surface.blit(letter_t,
                         (rect.x + 10, rect.centery - letter_t.get_height() // 2))

            opt_lines = self._wrap_text(q["opts"][i], self.font_opt, rect.width - 52)
            total_h = len(opt_lines) * (self.font_opt.get_height() + 2)
            oy = rect.centery - total_h // 2
            for ol in opt_lines:
                ot = self.font_opt.render(ol, True, (230, 225, 255))
                surface.blit(ot, (rect.x + 42, oy))
                oy += self.font_opt.get_height() + 2

        # Instrucción / feedback
        if self.state == "QUESTION":
            hint = self.font_small.render(
                "Presiona A / B / C / D  o  haz clic en una opción",
                True, (120, 115, 180))
            surface.blit(hint, hint.get_rect(centerx=px + pw // 2, y=py + 490))
        else:
            if self.feedback_correct:
                msg, col = "¡Correcto!", (80, 230, 100)
            else:
                msg, col = "Incorrecto", (230, 70, 70)
            fb_t = self.font_title.render(msg, True, col)
            surface.blit(fb_t, fb_t.get_rect(centerx=px + pw // 2, y=py + 480))

    def _draw_reward(self, surface, px, py, pw, ph):
        pulse = abs(math.sin(self.anim_timer * 3))
        col = (int(100 + 155 * pulse), int(180 + 35 * pulse), 80)
        t1 = self.font_title.render("¡Desafío completado!", True, col)
        surface.blit(t1, t1.get_rect(center=(px + pw // 2, py + 120)))

        t2 = self.font_body.render(
            "Respondiste correctamente las 3 preguntas.", True, (200, 200, 255))
        surface.blit(t2, t2.get_rect(center=(px + pw // 2, py + 165)))

        if self.reward_data:
            bw, bh = 380, 90
            bx = px + (pw - bw) // 2
            by = py + 210
            pygame.draw.rect(surface, (10, 40, 15), (bx, by, bw, bh), border_radius=8)
            pygame.draw.rect(surface, (60, 200, 80), (bx, by, bw, bh), 2, border_radius=8)
            rew_t = self.font_title.render("Recompensa obtenida:", True, (255, 215, 0))
            surface.blit(rew_t, rew_t.get_rect(centerx=px + pw // 2, y=by + 10))
            val_t = self.font_body.render(self.reward_data["label"], True, (140, 255, 160))
            surface.blit(val_t, val_t.get_rect(centerx=px + pw // 2, y=by + 52))

        h = self.hero
        stats = self.font_small.render(
            f"HP: {h.hp}/{h.max_hp}   Escudo: {h.shield}   Nivel: {h.level}",
            True, (170, 170, 220))
        surface.blit(stats, stats.get_rect(center=(px + pw // 2, py + 340)))

        cont = self.font_small.render(
            "Presiona ENTER para continuar", True, (140, 135, 200))
        alpha = int((math.sin(self.anim_timer * 4) + 1) / 2 * 255)
        temp = pygame.Surface(cont.get_size(), pygame.SRCALPHA)
        temp.fill((255, 255, 255, alpha))
        cont.blit(temp, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(cont, cont.get_rect(center=(px + pw // 2, py + 460)))

    def _draw_fail(self, surface, px, py, pw, ph):
        t1 = self.font_title.render("Desafío no superado", True, (220, 80, 80))
        surface.blit(t1, t1.get_rect(center=(px + pw // 2, py + 140)))

        t2 = self.font_body.render(
            "Fallaste una respuesta. Sin recompensa.", True, (200, 160, 160))
        surface.blit(t2, t2.get_rect(center=(px + pw // 2, py + 185)))

        t3 = self.font_small.render(
            "Sigue explorando y vuelve más preparado.", True, (160, 150, 180))
        surface.blit(t3, t3.get_rect(center=(px + pw // 2, py + 215)))

        if self.current_q < len(self.questions):
            q = self.questions[self.current_q]
            corr_text = q["opts"][q["correct"]]
            wrap = self._wrap_text(
                f"Respuesta correcta: {corr_text}", self.font_small, pw - 60)
            oy = py + 260
            for line in wrap:
                lt = self.font_small.render(line, True, (130, 200, 255))
                surface.blit(lt, lt.get_rect(centerx=px + pw // 2, y=oy))
                oy += lt.get_height() + 4

        cont = self.font_small.render(
            "Presiona ENTER para continuar", True, (140, 135, 200))
        alpha = int((math.sin(self.anim_timer * 4) + 1) / 2 * 255)
        temp = pygame.Surface(cont.get_size(), pygame.SRCALPHA)
        temp.fill((255, 255, 255, alpha))
        cont.blit(temp, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(cont, cont.get_rect(center=(px + pw // 2, py + 460)))

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _wrap_text(text: str, font: pygame.font.Font, max_w: int):
        words = text.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            if font.size(test)[0] <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines or [text]
