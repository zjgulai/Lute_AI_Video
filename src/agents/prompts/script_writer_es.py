"""Script Writer system prompt — Spanish edition.

Translated prompts and templates for Spanish-language script generation.
"""

SCRIPT_WRITER_SYSTEM_PROMPT_ES = """Eres un redactor publicitario galardonado especializado en videos cortos para marcas de alimentación infantil de venta directa al consumidor. Has escrito guiones que han generado millones de vistas para marcas de extractores de leche portátiles.

## Tu Tarea
Convierte briefs de contenido en guiones de video completos y listos para producción.

## Estructura del Guión (Video Corto en 5 Actos)

**[0-3s] GANCHO — Detén el Desplazamiento**
Objetivo: Evitar que el espectador se desplace en los primeros 1.5 segundos.
Estrategias:
- Punto de Dolor: "Extraer leche en el trabajo no debería sentirse como un castigo."
- Contra-Narrativa: "No necesitas encerrarte en un cuarto de almacén."
- Dato Impactante: "Las mamás pierden en promedio 2 horas de productividad por sesión de extracción."
- Gancho Visual: Describe una imagen impactante, sin palabras.
- Pregunta: "¿Qué harías con 5 horas extra a la semana?"

**[3-8s] PUNTO DE DOLOR — Hazlo Personal**
Objetivo: Hacer que el espectador piense "esta es MI vida."
- Expande el gancho a un escenario específico y relatable
- Usa detalles concretos (tiempo, lugar, sentimiento)
- La voz en off debe sonar como una amiga hablando, no como un comercial

**[8-20s] SOLUCIÓN — Entrada del Producto**
Objetivo: Mostrar cómo el producto resuelve el problema de forma natural.
- Introduce el producto mostrándolo en acción
- Enfócate en 1-2 PVU que aborden directamente el punto de dolor
- Muestra, no digas — describe lo visual del producto funcionando

**[20-35s] CONFIANZA — Por Qué Creernos**
Objetivo: Generar credibilidad para que el espectador se sienta seguro al comprar.
- Menciona certificaciones (FDA, CE) si es relevante
- Cita números reales (horas, niveles de dB, mmHg)
- Referencia a la comunidad de usuarias o reseñas
- Mantenlo factual, no jactancioso

**[35-45s] CTA — Próximo Paso Claro**
Objetivo: Decirle al espectador exactamente qué hacer.
- Una acción clara: "Enlace en la bio" / "Guarda esto" / "Compra ahora"
- Adapta el CTA a la plataforma
- Termina con una nota empoderadora

## Adaptaciones por Plataforma

| Plataforma | Ritmo | Estilo de Gancho | Estilo de CTA | Duración |
|---|---|---|---|---|
| TikTok | Rápido | Visual + pregunta | Enlace en bio | 15-45s |
| YouTube Shorts | Medio | Intención de búsqueda | Suscríbete + enlace | 15-60s |
| Facebook | Medio-lento | Resonancia emocional | Comenta + tienda | 30-60s |
| Shopify | Lento | Beneficio del producto | Añadir al carrito | 30-90s |

## Voz de Marca (Arquetipo Cuidador)

- **Cálida**: Como una amiga de confianza, no una vendedora
- **Empoderadora**: "Te mereces esto" no "Necesitas esto"
- **Real**: Reconoce la realidad desordenada de la extracción
- **Profesional**: Creíble pero no clínica

DO:
- "Te mereces extraer leche sin esconderte en un baño."
- "2,500 mamás calificaron esto con 4.8 estrellas por una razón."
- "Tu horario de extracción no debería dictar tu horario de reuniones."

DON'T:
- "¡Deja de perder el tiempo extrayendo!"
- "Otras extractoras son basura comparadas con esta."
- Cualquier afirmación médica sobre resultados de salud.

## Formato de Salida
Devuelve un array JSON de guiones, uno por brief:
```json
[
  {
    "id": "SCRIPT-BRIEF-001-ES",
    "brief_id": "BRIEF-001",
    "platform": "tiktok",
    "language": "es",
    "total_duration": 45.0,
    "segments": [
      {
        "segment_type": "hook",
        "start_time": 0.0,
        "end_time": 3.0,
        "voiceover": "Texto exacto que dirá el actor de voz",
        "visual_description": "Describe la toma para el storyboard",
        "text_overlay": "Texto en pantalla en este momento"
      }
    ],
    "hashtags": ["#hashtag1", "#hashtag2"],
    "cta_text": "Llamada a la acción final"
  }
]
```

Tipos de segmento: hook, pain_point, solution, trust_building, cta

Genera guiones ahora. Hazlos auténticos. Una mamá real debería verlos y decir "finalmente, alguien lo entiende."
"""

SCRIPT_WRITER_USER_MESSAGE_TEMPLATE_ES = """Escribe guiones para los siguientes briefs de contenido.

## Guías de Voz de Marca
{brand_guidelines_json}

## Briefs de Contenido
{briefs_json}

Para cada brief, escribe UN guión por plataforma objetivo. Sigue la estructura de 5 actos exactamente.
Asegúrate de que el texto de la voz en off sea español natural y conversacional — no texto de marketing.
"""

# ── Translated mock templates (3 core briefs) ──

_SCRIPT_TEMPLATES_ES = {
    "BRIEF-001": {  # Tutorial: limpiar el extractor en la oficina
        "hook": "Extraer leche en el trabajo no significa esconderse en un cuarto de almacén.",
        "hook_visual": "Pantalla dividida: mujer sonriendo en su escritorio vs cuarto de almacén vacío",
        "hook_overlay": "¿Limpiar en 2 min? Sí.",
        "pain": "Encontrar un lugar limpio para extraer ya es difícil. ¿Limpiar todo después? Aún más. Lavabos públicos, llevar piezas mojadas de un lado a otro.",
        "pain_visual": "Primer plano de piezas del extractor lavándose en el lavabo de la oficina, mujer mirando por encima del hombro",
        "pain_overlay": "La lucha de la limpieza es real",
        "solution": "El diseño a prueba de derrames del X1 y sus piezas de silicona se limpian en menos de 30 segundos. Sin nevera. Sin viajes incómodos al baño. Solo enjuaga, seca, y vuelve a tu bolso.",
        "solution_visual": "Manos enjuagando piezas del X1 bajo el grifo, corte rápido metiendo piezas secas en la bolsa",
        "solution_overlay": "Enjuague de 30 seg. Listo.",
        "trust": "Succión de grado hospitalario de 280mmHg. Aprobado por la FDA. Usado por más de 50,000 mamás que extraen leche en el trabajo cada día. Batería de 2.5 horas para todo tu turno.",
        "trust_visual": "Insignia de la FDA sobre el producto, luego cuadrícula de testimonios de mamás",
        "trust_overlay": "Aprobado FDA | 280mmHg",
        "cta": "Deja de esconderte en el cuarto de almacén. Consigue el X1 en el enlace de la bio. Tu pausa de extracción se acaba de volver mucho más simple.",
        "cta_visual": "Mujer saliendo de la oficina con confianza, bolso al hombro, producto visible en la mano",
        "cta_overlay": "Compra X1 Ahora",
        "cta_text": "Compra el Extractor X1 — enlace en la bio",
        "hashtags": ["#extracciontrabajo", "#extractorportatil", "#mama trabajadora", "#consejodeextraccion"],
    },
    "BRIEF-003": {  # Comparación de velocidad de configuración
        "hook": "5 minutos de montaje vs 30 segundos. Adivina a cuál me cambio.",
        "hook_visual": "Dos cronómetros lado a lado comenzando, extractor tradicional a la izquierda, X1 a la derecha",
        "hook_overlay": "5 min vs 30 seg",
        "pain": "Los extractores tradicionales significan destubar mangueras, buscar un enchufe, colocar bridas que no caben en tu bolso, y perder la mitad de tu descanso solo preparándote. Para cuando empiezas, ya has perdido tiempo valioso de extracción.",
        "pain_visual": "Montaje del extractor tradicional: mangueras enredadas, buscando enchufe, contenido del bolso volcado",
        "pain_overlay": "Tanto montaje. Tan poco tiempo.",
        "solution": "El X1 se ensambla en tres piezas. Sin tubos. Sin cables. Sin necesidad de enchufe. Ponlo en tu sostén, enciéndelo, y estás extrayendo en menos de 30 segundos. Así de simple.",
        "solution_visual": "Primer plano en cámara rápida: ensamblando piezas del X1, colocándolo en el sostén, presionando el botón de encendido",
        "solution_overlay": "Ensambla. Coloca. Extrae.",
        "trust": "La misma succión de grado hospitalario que las máquinas grandes. 220g de peso. Batería de 2.5 horas. Y tan silencioso que nadie a tu alrededor lo sabrá nunca.",
        "trust_visual": "Báscula mostrando el X1 junto a un extractor tradicional, medidor de sonido mostrando <40dB, icono de batería",
        "trust_overlay": "Mismo poder. 1/10 del tamaño.",
        "cta": "Tu tiempo es valioso. Deja de perderlo en montaje. Consigue el X1 en el enlace de la bio y empieza a extraer en 30 segundos.",
        "cta_visual": "Producto centrado, brillante, texto flotando a su lado",
        "cta_overlay": "Montaje 30s → Bio",
        "cta_text": "Ahorra 4.5 minutos por sesión — compra X1",
        "hashtags": ["#consejosdeextraccion", "#extractorportatil", "#comparacion", "#eficiencia"],
    },
    "BRIEF-005": {  # Unboxing
        "hook": "¿Qué hay realmente en la caja? Descubrámoslo juntos.",
        "hook_visual": "Manos abriendo una caja minimalista, luz suave, primer plano estilo ASMR",
        "hook_overlay": "Unboxing del X1",
        "pain": "La mayoría de los unboxings de extractores son abrumadores. 47 piezas. Un manual más grueso que tu mano. Piezas que ni siquiera reconoces. Terminas viendo tres tutoriales de YouTube antes de tu primera extracción.",
        "pain_visual": "Caja de extractor tradicional con docenas de piezas pequeñas desparramadas, expresión abrumada",
        "pain_overlay": "47 piezas. Cero idea por dónde empezar.",
        "solution": "Caja del X1: unidad de extracción x2, bridas x2, cable de carga USB-C, tarjeta de inicio rápido. Eso es todo. 7 piezas en total. Todo cabe en la palma de tu mano. Estarás extrayendo antes de terminar de leer esta frase.",
        "solution_visual": "Artículos colocados ordenadamente uno por uno sobre superficie blanca, mano ensamblando en tiempo real, producto completamente armado en menos de 10 segundos",
        "solution_overlay": "7 piezas. 30 segundos a tu primera extracción.",
        "trust": "Respaldado por la FDA, más de 50,000 mamás y una garantía de 2 años. Cada unidad probada para consistencia de succión. Y si algo sale mal, nuestro equipo de soporte responde en menos de 2 minutos.",
        "trust_visual": "Tarjeta de garantía en primer plano, ventana de chat de soporte mostrando respuesta rápida, mamá sonriendo mientras usa el producto",
        "trust_overlay": "2 años Garantía | 2 min Soporte",
        "cta": "¿Lista para vivir el unboxing más simple de tu vida? El X1 está en el enlace de la bio. ¿Qué esperas?",
        "cta_visual": "Producto completamente ensamblado sobre fondo limpio, luz cálida, texto 'Compra Ahora' flotando",
        "cta_overlay": "Compra el X1 ↑",
        "cta_text": "Pide el X1 — 7 piezas, 30 segundos para extraer",
        "hashtags": ["#unboxing", "#extractorportatil", "#consejoparamamas", "#mama primeriza"],
    },
}
