# kg-educacion

Plugin para conectar Claude o Codex al MCP de Horacio y recuperar currículum,
OA, marcos evaluativos y materiales docentes desde KG Educación. El KG es privado,
independiente y no afiliado a MINEDUC; la autoridad corresponde a las fuentes citadas.

## Instalación

```bash
claude plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
claude plugin install kg-educacion@southlab-marketplace

codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin add kg-educacion@southlab-marketplace
```

Obtén la key en **Horacio → Mi cuenta → API key para Codex y MCP** y ejecuta la
skill `setup` o `/kg-educacion:kg-setup`. El script solicita el secreto sin eco y configura
`HORACIO_MCP_API_KEY` para ambos clientes.

## Autorización

La key identifica una cuenta de Horacio. En cada request el servidor vuelve a evaluar:

- estado de la cuenta;
- features habilitados;
- colegio y alcance de datos;
- grant vigente de materiales.

La key no contiene ni amplía esos permisos. Para materiales, Horacio emite internamente
una capability corta ligada al usuario y al destino; el usuario no administra ese JWT
ni recibe la llave global del KG.

## Tools principales

| Tool | Uso |
|---|---|
| `consultar_curriculum` | OA, indicadores, programas, unidades, horas y progresiones. |
| `explorar_oa` | Selección y exploración de OA oficiales. |
| `consultar_recursos` | Textos y materiales dentro del grant vivo de la cuenta. |
| `consultar_marco_evaluacion` | Marcos y criterios evaluativos. |
| `evaluacion_preparar` / `evaluacion_guardar` | Flujo de evaluaciones. |
| `plan_preparar` / `plan_guardar` | Flujo de planificación anual. |
| `clase_crear` | Flujo de planificación de clase. |

## Principios

- No inventar OA, ids, citas ni contenido ausente.
- Distinguir evidencia fuente de síntesis del modelo.
- No entregar ítems fuente protegidos ni sus claves.
- No pedir capabilities o headers adicionales al usuario.
- Ante una denegación, revisar permisos de la cuenta en vez de regenerar la key.
