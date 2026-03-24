# -*- coding: utf-8 -*-
"""Extrae cláusulas Segunda..Vigésima Tercera desde contract_fraterna.htm."""
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "contract_fraterna.htm"
OUT = ROOT / "apps" / "templates" / "home" / "partials" / "contrato_fraterna_clausulas_cuerpo.html"


def text_from_tag(tag):
    if BeautifulSoup is None:
        return ""
    return " ".join(tag.get_text(separator=" ", strip=True).split())


def is_subtitle_bold_p(p_tag):
    """Títulos que en Word van como <p><b><u>... (p. ej. Décima Segunda)."""
    b = p_tag.find("b")
    if not b:
        return None
    t = text_from_tag(b)
    if not t:
        return None
    if re.match(
        r"^(Décima (Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|Séptima|Octava|Novena|Décima)|Vigésima)\b",
        t,
        re.I,
    ):
        return t
    return None


def merge_split_paragraphs(parts):
    """Une párrafos partidos por saltos de sección en el HTML de Word (p. ej. 'y sin' / 'necesidad')."""
    merged = []
    i = 0
    while i < len(parts):
        cur = parts[i]
        if i + 1 < len(parts):
            # extraer texto plano aproximado
            m_end = re.search(r">([^<]+)</p>\s*$", cur)
            m_start = re.search(r"^<p class=\"clausula-p\">([^<]+)", parts[i + 1])
            if m_end and m_start:
                a, b = m_end.group(1).strip(), m_start.group(1).strip()
                if a.endswith("y sin") and b.startswith("necesidad"):
                    inner = m_end.group(1) + " " + m_start.group(1)
                    cur = re.sub(r">[^<]+</p>\s*$", f">{inner}</p>", cur)
                    i += 2
                    merged.append(cur)
                    continue
        merged.append(cur)
        i += 1
    return merged


def main():
    lines = SRC.read_text(encoding="cp1252", errors="replace").splitlines(keepends=True)
    start_idx = 4395
    end_line = None
    for i, ln in enumerate(lines):
        if i < start_idx:
            continue
        if "Las" in ln and "Partes, sabedoras" in "".join(lines[i : i + 3]):
            end_line = i
            break
    if end_line is None:
        print("Could not find end marker")
        return 1
    chunk = "".join(lines[start_idx:end_line])
    print("Lines", start_idx + 1, "to", end_line, "chars", len(chunk))

    if BeautifulSoup is None:
        print("pip install beautifulsoup4")
        return 1

    soup = BeautifulSoup(chunk, "html.parser")
    parts = []
    for el in soup.find_all(["h2", "p"]):
        if el.name == "h2":
            t = text_from_tag(el)
            if not t:
                continue
            parts.append(f'<p class="clausula-titulo">{t}</p>')
            continue

        if el.name != "p" or not el.get("class"):
            continue
        cls = " ".join(el.get("class", []))
        if not any(x in cls for x in ("MsoBodyText", "MsoListParagraph", "MsoNormal")):
            continue

        st = is_subtitle_bold_p(el)
        if st:
            parts.append(f'<p class="clausula-titulo">{st}</p>')
            continue

        t = text_from_tag(el)
        if not t or len(t) < 2:
            continue

        if "MsoListParagraph" in cls:
            parts.append(f'<p class="clausula-lista-inciso">{t}</p>')
        else:
            parts.append(f'<p class="clausula-p">{t}</p>')

    parts = merge_split_paragraphs(parts)
    body = "\n".join(parts)
    # Ajustes respecto al HTML de Word (doble "para el", inciso (ii), numeración errónea en lista)
    body = body.replace(
        "para el para el Estado de Nuevo León",
        "para el Estado de Nuevo León",
    )
    body = body.replace(
        "(ii) El hecho de que el o Residente no ocupe",
        "(ii) El hecho de que el Arrendatario o el Residente no ocupe",
    )
    body = body.replace(
        ">1 Infraestructura del departamento</p>",
        ">· Infraestructura del departamento</p>",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "{% comment %} Auto-extraído de contract_fraterna.htm (Segunda–Vigésima Tercera). Revisar. {% endcomment %}\n"
        + body,
        encoding="utf-8",
    )
    print("Wrote", OUT, "paragraphs", len(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
