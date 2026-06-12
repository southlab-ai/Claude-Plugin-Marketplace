---
name: setup
description: Configurar el acceso al MCP de kg-educacion — crear cuenta (usuario+contraseña), generar una API key y dejarla en KG_API_KEY. Úsala la primera vez o si el MCP responde 401.
---

# Configurar kg-educacion (cuenta + API key)

El MCP `kg-educacion` requiere una **API key** propia (el servicio es de pago por consulta).
El usuario crea una cuenta y desde ahí genera keys revocables. Guía al usuario así:

## 1. Crear la cuenta (una vez)
```bash
curl -s -X POST https://kg.southlab.ai/account/register \
  -H "Content-Type: application/json" \
  -d '{"username":"TU_USUARIO","password":"TU_CONTRASEÑA"}'
```

## 2. Crear una API key
```bash
curl -s -X POST https://kg.southlab.ai/account/keys \
  -H "Content-Type: application/json" \
  -d '{"username":"TU_USUARIO","password":"TU_CONTRASEÑA","label":"mi-notebook"}'
```
La respuesta trae `api_key` (formato `kg_live_…`). **Se muestra una sola vez** — guárdala.

## 3. Dejarla en el entorno como KG_API_KEY
- macOS/Linux (zsh/bash): `echo 'export KG_API_KEY=kg_live_…' >> ~/.zshrc && source ~/.zshrc`
- El plugin ya apunta el MCP a `https://kg.southlab.ai/mcp` con `Authorization: Bearer ${KG_API_KEY}`.

## 4. Verificar
Reinicia Claude Code / Codex y pregunta algo curricular (ej. "qué OA tiene Lenguaje 4° básico").
Si responde con citas, está conectado. Si da 401, la key falta o está revocada.

## Gestión de keys
- Listar: `POST /account/keys/list` con `{username,password}`.
- Revocar: `POST /account/keys/revoke` con `{username,password,key_id}`.
