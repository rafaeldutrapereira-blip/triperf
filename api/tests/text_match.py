"""
Helper para asserts estáticos tolerantes al formateo.

Los tests de contenido (HTML/CSS/JS) comparaban strings literales. Cuando el
repo pasó por Prettier (2026-10-27/28: commits bd2859b "formatea páginas",
6e78b5d "reformatea landing.html", 9445fa2 y 5dddcfc) cambió el espaciado y el
estilo de comillas (dobles -> simples), y varios asserts empezaron a fallar
sin que la app hubiera cambiado de comportamiento.

`squash()` normaliza comillas simples a dobles y elimina TODO el espacio en
blanco de ambos lados de la comparación, así el test sigue verificando que el
código está y hace lo que dice, sin quedar atado a cómo lo formatea Prettier.
"""
import re


def squash(text: str) -> str:
    """Devuelve el texto comparable sin depender de espaciado ni de comillas."""
    return re.sub(r"\s+", "", str(text).replace("'", '"'))
