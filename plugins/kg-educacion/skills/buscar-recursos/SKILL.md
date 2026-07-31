---
name: buscar-recursos
description: Use when the user asks for Chilean curriculum evidence, OA, textbooks, teacher guides or teaching resources through Horacio and KG Educación.
---

# Buscar evidencia y materiales

1. Usa `consultar_curriculum` para OA, indicadores, programas, unidades curriculares,
   horas, progresiones y evidencia pedagógica.
2. Usa `explorar_oa` cuando el target curricular sea ambiguo o el usuario quiera elegir OA.
3. Usa `consultar_recursos` para textos, guías y materiales. Horacio limita el resultado
   al feature y grant vivos de la cuenta y gestiona la capability internamente.
4. Presenta título, tipo, asignatura, curso, URL y procedencia que entregue la tool.

No pidas tokens de cabecera de acceso ni claims técnicos al usuario. No confundas falta de permiso con
ausencia de material. Ante 401 usa `setup`; ante función no habilitada revisa la cuenta.
No inventes OA, enlaces, citas o texto que la tool no devolvió.
