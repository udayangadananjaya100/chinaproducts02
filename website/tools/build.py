#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data & Image Extraction Pipeline (website/tools/build.py)
- Parses .xlsx files directly using Python standard library (zipfile + xml.etree.ElementTree) and Pillow (PIL).
- Supports BOTH:
  1. Standard OpenXML floating drawing anchors (xl/drawings/drawing*.xml -> twoCellAnchor / oneCellAnchor)
  2. WPS Office in-cell =DISPIMG("ID_...", 1) formulas mapped via xl/cellimages.xml and xl/_rels/cellimages.xml.rels
- Converts and deduplicates every extracted image into two optimized WebP files in website/images/:
  - Thumbnail (p001_t.webp, max side 360px, quality 82)
  - Large high-res (p001_l.webp, max side 1100px, quality 85)
- Translates every product name (zh, en, si, es) and variant badge into natural, accurate Sinhala (si), English (en), Chinese (zh), and Spanish (es).
- Categorizes products via keyword classification and runs the SL-WPI 100-Point Sea Cargo scoring engine.
- Outputs window.CATALOG = { ... }; inside website/data/products.js.
"""

import glob
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from PIL import Image

# Ensure local import works
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
WEBSITE_DIR = os.path.dirname(TOOLS_DIR)
ROOT_DIR = os.path.dirname(WEBSITE_DIR)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from generate_winning_scores import score_all_products

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "etc": "http://www.wps.cn/officeDocument/2017/etCustomData",
}
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# Complete translation dictionary for all Chinese mirror model names
PRODUCT_TRANSLATIONS = {
    # File 1: Full-Wrap Velvet / Upholstered Mirrors (全包软包穿衣镜)
    "绒布不规则波浪": {
        "code_prefix": "XW-VP01",
        "en": "Velvet Irregular Wavy Full-Length Dressing Mirror",
        "si": "අක්‍රමවත් රැලි හැඩැති වෙල්වට් සම්පූර්ණ දිග රූපලාවන්‍ය කණ්ණාඩිය (Velvet Irregular Wavy Mirror)",
        "es": "Espejo de Cuerpo Entero Ondulado Irregular Tapizado en Terciopelo",
    },
    "绒布红球": {
        "code_prefix": "XW-VP02",
        "en": "Velvet Bubble Sphere Full-Length Dressing Mirror",
        "si": "ගෝලාකාර බෝල මෝස්තරයේ වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Bubble Sphere Mirror)",
        "es": "Espejo de Cuerpo Entero con Esferas Tapizado en Terciopelo",
    },
    "绒布花生": {
        "code_prefix": "XW-VP03",
        "en": "Velvet Peanut Curve Full-Length Dressing Mirror",
        "si": "රටකජු වක්‍ර හැඩැති වෙල්වට් සම්පූර්ණ දිග රූපලාවන්‍ය කණ්ණාඩිය (Velvet Peanut Curve Mirror)",
        "es": "Espejo de Cuerpo Entero Silueta Cacahuete de Terciopelo",
    },
    "绒布齐边波浪": {
        "code_prefix": "XW-VP04",
        "en": "Velvet Straight-Edge Wavy Full-Length Mirror",
        "si": "සමතල දාර රැලි හැඩැති වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Straight-Edge Wavy Mirror)",
        "es": "Espejo de Cuerpo Entero Ondulado de Borde Recto en Terciopelo",
    },
    "绒布双波浪": {
        "code_prefix": "XW-VP05",
        "en": "Velvet Double-Wave Full-Length Dressing Mirror",
        "si": "ද්විත්ව රැලි හැඩැති වෙල්වට් සම්පූර්ණ දිග රූපලාවන්‍ය කණ්ණාඩිය (Velvet Double-Wave Mirror)",
        "es": "Espejo de Cuerpo Entero Doble Onda de Terciopelo",
    },
    "绒布四面波浪": {
        "code_prefix": "XW-VP06",
        "en": "Velvet All-Around Four-Sided Wavy Mirror",
        "si": "සිව්පස රැලි හැඩැති වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet 4-Sided Wavy Mirror)",
        "es": "Espejo de Cuerpo Entero Ondulado en 4 Lados de Terciopelo",
    },
    "绒布双平底波浪": {
        "code_prefix": "XW-VP07",
        "en": "Velvet Flat-Base Double Wavy Full-Length Mirror",
        "si": "සමතල පාදමක් සහිත ද්විත්ව රැලි වෙල්වට් කණ්ණාඩිය (Velvet Flat-Base Wavy Mirror)",
        "es": "Espejo de Cuerpo Entero Doble Onda Base Plana de Terciopelo",
    },
    "绒布细边芒果": {
        "code_prefix": "XW-VP08",
        "en": "Velvet Slim-Rim Mango Asymmetrical Mirror",
        "si": "සිහින් දාර අඹ හැඩැති වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Slim-Rim Mango Mirror)",
        "es": "Espejo de Cuerpo Entero Forma Mango Borde Fino de Terciopelo",
    },
    "绒布内云朵": {
        "code_prefix": "XW-VP09",
        "en": "Velvet Inner-Cloud Contour Full-Length Mirror",
        "si": "ඇතුළත වළාකුළු හැඩැති වෙල්වට් රූපලාවන්‍ය කණ්ණාඩිය (Velvet Inner-Cloud Mirror)",
        "es": "Espejo de Cuerpo Entero Contorno Nube Interior de Terciopelo",
    },
    "绒布钻石": {
        "code_prefix": "XW-VP10",
        "en": "Velvet Tufted Diamond Full-Length Dressing Mirror",
        "si": "දියමන්ති මෝස්තරයේ වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Diamond Mirror)",
        "es": "Espejo de Cuerpo Entero Diseño Diamante de Terciopelo",
    },
    "绒布宽边芒果": {
        "code_prefix": "XW-VP11",
        "en": "Velvet Wide-Rim Mango Full-Length Mirror",
        "si": "පළල් දාර අඹ හැඩැති වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Wide-Rim Mango Mirror)",
        "es": "Espejo de Cuerpo Entero Forma Mango Borde Ancho de Terciopelo",
    },
    "绒布齿形": {
        "code_prefix": "XW-VP12",
        "en": "Velvet Scalloped Gear-Edge Full-Length Mirror",
        "si": "දැති දාර හැඩැති වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Scalloped Edge Mirror)",
        "es": "Espejo de Cuerpo Entero Borde Dentado de Terciopelo",
    },
    "绒布元宝": {
        "code_prefix": "XW-VP13",
        "en": "Velvet Ingot Arch Full-Length Dressing Mirror",
        "si": "වක්‍රාකාර උඩු දාර සහිත වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Ingot Arch Mirror)",
        "es": "Espejo de Cuerpo Entero Arco Clásico de Terciopelo",
    },
    "绒布大C": {
        "code_prefix": "XW-VP14",
        "en": "Velvet Sculpted C-Curve Luxury Floor Mirror",
        "si": "C-හැඩැති සුඛෝපභෝගී වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet C-Curve Floor Mirror)",
        "es": "Espejo de Piso Curva C Escultural de Terciopelo",
    },
    "绒布大U": {
        "code_prefix": "XW-VP15",
        "en": "Velvet U-Arch Padded Luxury Floor Mirror",
        "si": "U-ආරුක්කු හැඩැති සුඛෝපභෝගී වෙල්වට් කණ්ණාඩිය (Velvet U-Arch Floor Mirror)",
        "es": "Espejo de Piso Arco U Acolchado de Terciopelo",
    },
    "绒布大方": {
        "code_prefix": "XW-VP16",
        "en": "Velvet Grand Rectangular Padded Floor Mirror",
        "si": "සෘජුකෝණාස්‍රාකාර සුඛෝපභෝගී වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet Grand Rectangular Mirror)",
        "es": "Espejo de Piso Rectangular Grande Acolchado de Terciopelo",
    },
    "绒布大H": {
        "code_prefix": "XW-VP17",
        "en": "Velvet H-Frame Designer Padded Floor Mirror",
        "si": "H-හැඩැති විශේෂිත වෙල්වට් සම්පූර්ණ දිග කණ්ණාඩිය (Velvet H-Frame Designer Mirror)",
        "es": "Espejo de Piso Diseño H Acolchado de Terciopelo",
    },

    # File 2: Hanging Wall / Home Mirrors (挂钩家居镜)
    "252A1小平底": {
        "code_prefix": "XW-252A1",
        "zh_clean": "252A1 小平底挂钩镜",
        "en": "252A1 Compact Arched Flat-Base Hanging Wall Mirror",
        "si": "කුඩා පැතලි පාදමක් සහිත බිත්ති එල්ලන රූපලාවන්‍ය කණ්ණාඩිය (252A1 Small Flat-Base Hanging Mirror)",
        "es": "Espejo Colgante de Pared Compacto Base Plana 252A1",
    },
    "255A2小椭圆": {
        "code_prefix": "XW-255A2",
        "zh_clean": "255A2 小椭圆挂钩镜",
        "en": "255A2 Compact Oval Hanging Wall Mirror",
        "si": "කුඩා ඕවලාකාර බිත්ති එල්ලන රූපලාවන්‍ය කණ්ණාඩිය (255A2 Small Oval Hanging Mirror)",
        "es": "Espejo Colgante de Pared Ovalado Compacto 255A2",
    },
    "257A3小圆": {
        "code_prefix": "XW-257A3",
        "zh_clean": "257A3 小圆挂钩镜",
        "en": "257A3 Compact Round Hanging Wall Mirror",
        "si": "කුඩා වටකුරු බිත්ති එල්ලන රූපලාවන්‍ය කණ්ණාඩිය (257A3 Small Round Hanging Mirror)",
        "es": "Espejo Colgante de Pared Redondo Compacto 257A3",
    },
    "258A4小胖方": {
        "code_prefix": "XW-258A4",
        "zh_clean": "258A4 小胖方挂钩镜",
        "en": "258A4 Compact Soft-Square Hanging Wall Mirror",
        "si": "කුඩා වටකුරු කොන් සහිත හතරැස් බිත්ති කණ්ණාඩිය (258A4 Small Soft-Square Mirror)",
        "es": "Espejo Colgante de Pared Cuadrado Suave Compacto 258A4",
    },
    "261A5小长方": {
        "code_prefix": "XW-261A5",
        "zh_clean": "261A5 小长方挂钩镜",
        "en": "261A5 Compact Rectangular Hanging Wall Mirror",
        "si": "කුඩා සෘජුකෝණාස්‍රාකාර බිත්ති එල්ලන කණ්ණාඩිය (261A5 Small Rectangular Hanging Mirror)",
        "es": "Espejo Colgante de Pared Rectangular Compacto 261A5",
    },
    "252小平底": {
        "code_prefix": "XW-252",
        "zh_clean": "252 中号平底挂钩镜",
        "en": "252 Medium Arched Flat-Base Hanging Wall Mirror",
        "si": "මධ්‍යම ප්‍රමාණයේ පැතලි පාදමක් සහිත බිත්ති කණ්ණාඩිය (252 Medium Flat-Base Wall Mirror)",
        "es": "Espejo Colgante de Pared Mediano Base Plana 252",
    },
    "255小椭圆": {
        "code_prefix": "XW-255",
        "zh_clean": "255 中号椭圆挂钩镜",
        "en": "255 Medium Oval Hanging Wall Mirror",
        "si": "මධ්‍යම ප්‍රමාණයේ ඕවලාකාර බිත්ති එල්ලන කණ්ණාඩිය (255 Medium Oval Wall Mirror)",
        "es": "Espejo Colgante de Pared Ovalado Mediano 255",
    },
    "257小圆": {
        "code_prefix": "XW-257",
        "zh_clean": "257 中号圆挂钩镜",
        "en": "257 Medium Round Hanging Wall Mirror",
        "si": "මධ්‍යම ප්‍රමාණයේ වටකුරු බිත්ති එල්ලන කණ්ණාඩිය (257 Medium Round Wall Mirror)",
        "es": "Espejo Colgante de Pared Redondo Mediano 257",
    },
    "258小胖方": {
        "code_prefix": "XW-258",
        "zh_clean": "258 中号胖方挂钩镜",
        "en": "258 Medium Soft-Square Hanging Wall Mirror",
        "si": "මධ්‍යම ප්‍රමාණයේ වටකුරු කොන් හතරැස් බිත්ති කණ්ණාඩිය (258 Medium Soft-Square Wall Mirror)",
        "es": "Espejo Colgante de Pared Cuadrado Suave Mediano 258",
    },
    "261小长方": {
        "code_prefix": "XW-261",
        "zh_clean": "261 中号长方挂钩镜",
        "en": "261 Medium Rectangular Hanging Wall Mirror",
        "si": "මධ්‍යම ප්‍රමාණයේ සෘජුකෝණාස්‍රාකාර බිත්ති කණ්ණාඩිය (261 Medium Rectangular Wall Mirror)",
        "es": "Espejo Colgante de Pared Rectangular Mediano 261",
    },
    "251大平底": {
        "code_prefix": "XW-251",
        "zh_clean": "251 大号平底挂钩镜",
        "en": "251 Large Arched Flat-Base Hanging Wall Mirror",
        "si": "විශාල පැතලි පාදමක් සහිත බිත්ති එල්ලන කණ්ණාඩිය (251 Large Flat-Base Wall Mirror)",
        "es": "Espejo Colgante de Pared Grande Base Plana 251",
    },
    "253大椭圆": {
        "code_prefix": "XW-253",
        "zh_clean": "253 大号椭圆挂钩镜",
        "en": "253 Large Oval Hanging Wall Mirror",
        "si": "විශාල ඕවලාකාර බිත්ති එල්ලන රූපලාවන්‍ය කණ්ණාඩිය (253 Large Oval Wall Mirror)",
        "es": "Espejo Colgante de Pared Ovalado Grande 253",
    },
    "256大圆": {
        "code_prefix": "XW-256",
        "zh_clean": "256 大号圆挂钩镜",
        "en": "256 Large Round Hanging Wall Mirror",
        "si": "විශාල වටකුරු බිත්ති එල්ලන රූපලාවන්‍ය කණ්ණාඩිය (256 Large Round Wall Mirror)",
        "es": "Espejo Colgante de Pared Redondo Grande 256",
    },
    "259大胖方": {
        "code_prefix": "XW-259",
        "zh_clean": "259 大号胖方挂钩镜",
        "en": "259 Large Soft-Square Hanging Wall Mirror",
        "si": "විශාල වටකුරු කොන් හතරැස් බිත්ති කණ්ණාඩිය (259 Large Soft-Square Wall Mirror)",
        "es": "Espejo Colgante de Pared Cuadrado Suave Grande 259",
    },
    "260大长方": {
        "code_prefix": "XW-260",
        "zh_clean": "260 大号长方挂钩镜",
        "en": "260 Large Rectangular Hanging Wall Mirror",
        "si": "විශාල සෘජුකෝණාස්‍රාකාර බිත්ති එල්ලන කණ්ණාඩිය (260 Large Rectangular Wall Mirror)",
        "es": "Espejo Colgante de Pared Rectangular Grande 260",
    },
    "262特大平底": {
        "code_prefix": "XW-262",
        "zh_clean": "262 特大平底挂钩镜",
        "en": "262 Extra-Large Arched Flat-Base Wall Mirror",
        "si": "ඉතා විශාල (XL) පැතලි පාදමක් සහිත බිත්ති කණ්ණාඩිය (262 XL Flat-Base Wall Mirror)",
        "es": "Espejo Colgante de Pared Extra Grande Base Plana 262",
    },
    "263特大椭圆": {
        "code_prefix": "XW-263",
        "zh_clean": "263 特大椭圆挂钩镜",
        "en": "263 Extra-Large Oval Hanging Wall Mirror",
        "si": "ඉතා විශාල (XL) ඕවලාකාර බිත්ති එල්ලන කණ්ණාඩිය (263 XL Oval Wall Mirror)",
        "es": "Espejo Colgante de Pared Ovalado Extra Grande 263",
    },
    "265特大胖方": {
        "code_prefix": "XW-265",
        "zh_clean": "265 特大胖方挂钩镜",
        "en": "265 Extra-Large Soft-Square Hanging Wall Mirror",
        "si": "ඉතා විශාල (XL) වටකුරු කොන් හතරැස් බිත්ති කණ්ණාඩිය (265 XL Soft-Square Wall Mirror)",
        "es": "Espejo Colgante de Pared Cuadrado Suave Extra Grande 265",
    },
    "266特大长方": {
        "code_prefix": "XW-266",
        "zh_clean": "266 特大长方挂钩镜",
        "en": "266 Extra-Large Rectangular Hanging Wall Mirror",
        "si": "ඉතා විශාල (XL) සෘජුකෝණාස්‍රාකාර බිත්ති කණ්ණාඩිය (266 XL Rectangular Wall Mirror)",
        "es": "Espejo Colgante de Pared Rectangular Extra Grande 266",
    },

    # File 3: 360° Rotating & Storage Mirrors (旋转镜子)
    "小熊旋转": {
        "code_prefix": "XW-RT01",
        "en": "360° Rotating Bear Silhouette Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන වලස් හැඩැති සම්පූර්ණ දිග කණ්ණාඩිය (360° Rotating Bear Mirror)",
        "es": "Espejo Giratorio 360° de Cuerpo Entero Silueta Oso",
    },
    "两头圆洞洞板": {
        "code_prefix": "XW-RT02",
        "en": "360° Rotating Rounded-End Pegboard Storage Mirror",
        "si": "අංශක 360 කැරකෙන සිදුරු පුවරු (Pegboard) රාක්ක කණ්ණාඩිය (Rotating Pegboard Mirror)",
        "es": "Espejo Giratorio 360° con Tablero Perforado Organizador",
    },
    "波浪": {
        "code_prefix": "XW-RT03",
        "zh_clean": "波浪旋转穿衣镜",
        "en": "360° Rotating Wavy Contour Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන රැලි හැඩැති සම්පූර්ණ දිග කණ්ණාඩිය (360° Rotating Wavy Mirror)",
        "es": "Espejo Giratorio 360° de Cuerpo Entero Contorno Ondulado",
    },
    "波浪洞洞": {
        "code_prefix": "XW-RT04",
        "zh_clean": "波浪洞洞板旋转镜",
        "en": "360° Rotating Wavy Pegboard Organizer Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන රැලි හැඩැති සිදුරු පුවරු (Pegboard) කණ්ණාඩිය (Wavy Pegboard Mirror)",
        "es": "Espejo Giratorio 360° Ondulado con Tablero Perforado",
    },
    "鱼尾": {
        "code_prefix": "XW-RT05",
        "zh_clean": "鱼尾旋转穿衣镜",
        "en": "360° Rotating Fishtail Curve Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන මාළු වලිග හැඩැති සම්පූර්ණ දිග කණ්ණාඩිය (360° Fishtail Rotating Mirror)",
        "es": "Espejo Giratorio 360° Diseño Cola de Sirena",
    },
    "方形旋转": {
        "code_prefix": "XW-RT06",
        "en": "360° Rotating Classic Rectangular Stand Mirror",
        "si": "අංශක 360 කැරකෙන සෘජුකෝණාස්‍රාකාර සම්පූර්ණ දිග කණ්ණාඩිය (360° Rectangular Rotating Mirror)",
        "es": "Espejo Giratorio 360° Rectangular Clásico de Pie",
    },
    "两头圆简约": {
        "code_prefix": "XW-RT07",
        "en": "Minimalist Capsule Rounded-End Rotating Mirror",
        "si": "සරල කැප්සියුල හැඩැති කැරකෙන සම්පූර්ණ දිග කණ්ණාඩිය (Minimalist Capsule Rotating Mirror)",
        "es": "Espejo Giratorio Minimalista Forma Cápsula",
    },
    "拱形旋转": {
        "code_prefix": "XW-RT08",
        "en": "360° Rotating Arch Full-Length Dressing Mirror",
        "si": "අංශක 360 කැරකෙන ආරුක්කු හැඩැති රූපලාවන්‍ය කණ්ණාඩිය (360° Arch Rotating Mirror)",
        "es": "Espejo Giratorio 360° Diseño Arco de Cuerpo Entero",
    },
    "推拉镜": {
        "code_prefix": "XW-RT09",
        "en": "Sliding Pull-Out Wardrobe Hidden Storage Mirror",
        "si": "අල්මාරි සඳහා ස්ලයිඩින් (Pull-Out) ඇද ගත හැකි කණ්ණාඩිය (Sliding Wardrobe Mirror)",
        "es": "Espejo Deslizante Extraíble para Armario y Vestidor",
    },
    "小猫旋转镜": {
        "code_prefix": "XW-RT10",
        "en": "360° Rotating Cat-Ear Silhouette Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන පූස් කන් හැඩැති සම්පූර්ණ දිග කණ්ණාඩිය (Cat-Ear Rotating Mirror)",
        "es": "Espejo Giratorio 360° Silueta Orejas de Gato",
    },
    "书架方形穿衣镜": {
        "code_prefix": "XW-RT11",
        "en": "2-in-1 Rectangular Bookshelf & Coat Rack Rotating Mirror",
        "si": "පොත් රාක්කයක් සහිත සෘජුකෝණාස්‍රාකාර කැරකෙන කණ්ණාඩිය (Bookshelf Rectangular Rotating Mirror)",
        "es": "Espejo Giratorio 2 en 1 Rectangular con Estantería",
    },
    "书架拱形穿衣镜": {
        "code_prefix": "XW-RT12",
        "en": "2-in-1 Arch Bookshelf & Storage Rotating Mirror",
        "si": "පොත් රාක්කයක් සහිත ආරුක්කු හැඩැති කැරකෙන කණ්ණාඩිය (Bookshelf Arch Rotating Mirror)",
        "es": "Espejo Giratorio 2 en 1 Diseño Arco con Estantería",
    },
    "波浪旋转": {
        "code_prefix": "XW-RT13",
        "en": "360° Rotating Scalloped Wave Full-Length Mirror",
        "si": "අංශක 360 කැරකෙන රැලි දාර සම්පූර්ණ දිග කණ්ණාඩිය (Scalloped Wave Rotating Mirror)",
        "es": "Espejo Giratorio 360° Borde Ondulado de Cuerpo Entero",
    },
    "书架波浪穿衣镜": {
        "code_prefix": "XW-RT14",
        "en": "2-in-1 Wavy Bookshelf & Storage Rotating Mirror",
        "si": "පොත් රාක්කයක් සහිත රැලි හැඩැති කැරකෙන කණ්ණාඩිය (Bookshelf Wavy Rotating Mirror)",
        "es": "Espejo Giratorio 2 en 1 Ondulado con Estantería",
    },
    "书架小熊穿衣镜": {
        "code_prefix": "XW-RT15",
        "en": "2-in-1 Bear Silhouette Bookshelf Rotating Mirror",
        "si": "පොත් රාක්කයක් සහිත වලස් හැඩැති කැරකෙන කණ්ණාඩිය (Bookshelf Bear Rotating Mirror)",
        "es": "Espejo Giratorio 2 en 1 Silueta Oso con Estantería",
    },
    "双面熊": {
        "code_prefix": "XW-RT16",
        "zh_clean": "双面小熊旋转穿衣镜",
        "en": "Double-Sided Bear 360° Rotating Full-Length Mirror",
        "si": "දෙපසම කණ්ණාඩි සහිත වලස් හැඩැති කැරකෙන කණ්ණාඩිය (Double-Sided Bear Rotating Mirror)",
        "es": "Espejo Giratorio 360° Doble Cara Silueta Oso",
    },

    # File 4: Vintage Wood-Board Stand Mirrors (中古板镜)
    "中古-波浪（支架款）": {
        "code_prefix": "XW-WB01",
        "en": "Vintage Wavy Wood-Backed Floor Stand Mirror",
        "si": "වින්ටේජ් රැලි හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Wavy Stand Mirror)",
        "es": "Espejo Vintage Ondulado de Pie con Soporte de Madera",
    },
    "中古-芒果（支架款）": {
        "code_prefix": "XW-WB02",
        "en": "Vintage Mango Curve Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් අඹ හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Mango Stand Mirror)",
        "es": "Espejo Vintage Forma Mango de Pie con Soporte",
    },
    "中古-海豚（支架款）": {
        "code_prefix": "XW-WB03",
        "en": "Vintage Dolphin Curve Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් ඩොල්ෆින් වක්‍ර හැඩැති ආධාරක කණ්ණාඩිය (Vintage Dolphin Curve Stand Mirror)",
        "es": "Espejo Vintage Silueta Delfín de Pie con Soporte",
    },
    "中古-花生（支架款）": {
        "code_prefix": "XW-WB04",
        "en": "Vintage Peanut Silhouette Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් රටකජු හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Peanut Stand Mirror)",
        "es": "Espejo Vintage Silueta Cacahuete de Pie con Soporte",
    },
    "中古-方圆（支架款）": {
        "code_prefix": "XW-WB05",
        "en": "Vintage Soft-Arch Square-Round Wood Stand Mirror",
        "si": "වින්ටේජ් වටකුරු-හතරැස් ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Square-Round Stand Mirror)",
        "es": "Espejo Vintage Cuadrado Redondeado con Soporte",
    },
    "中古-异形云朵（支架款）": {
        "code_prefix": "XW-WB06",
        "en": "Vintage Asymmetric Cloud Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් අක්‍රමවත් වළාකුළු හැඩැති ආධාරක කණ්ණාඩිය (Vintage Asymmetric Cloud Mirror)",
        "es": "Espejo Vintage Nube Asimétrica de Pie con Soporte",
    },
    "中古-拱形（支架款）": {
        "code_prefix": "XW-WB07",
        "en": "Vintage Classic Arch Wood-Backed Floor Stand Mirror",
        "si": "වින්ටේජ් ආරුක්කු හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Arch Stand Mirror)",
        "es": "Espejo Vintage Arco Clásico de Pie con Soporte",
    },
    "中古-大云朵（支架款）": {
        "code_prefix": "XW-WB08",
        "en": "Vintage Grand Cloud Contour Wood Stand Mirror",
        "si": "වින්ටේජ් විශාල වළාකුළු හැඩැති ආධාරක කණ්ණාඩිය (Vintage Grand Cloud Stand Mirror)",
        "es": "Espejo Vintage Gran Nube de Pie con Soporte",
    },
    "中古-小熊（支架款）": {
        "code_prefix": "XW-WB09",
        "en": "Vintage Bear Silhouette Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් වලස් හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Bear Stand Mirror)",
        "es": "Espejo Vintage Silueta Oso de Pie con Soporte",
    },
    "中古-小波浪（支架款）": {
        "code_prefix": "XW-WB10",
        "en": "Vintage Fine Ripple Wave Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් කුඩා රැලි හැඩැති ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage Fine Wave Stand Mirror)",
        "es": "Espejo Vintage Onda Fina de Pie con Soporte",
    },
    "中古-可乐挂钩（支架款）": {
        "code_prefix": "XW-WB11",
        "en": "Vintage Bottle-Curve Stand Mirror with Side Coat Hooks",
        "si": "ඇඳුම් එල්ලන කොකු සහිත වින්ටේජ් වක්‍රාකාර ආධාරක කණ්ණාඩිය (Vintage Hook Stand Mirror)",
        "es": "Espejo Vintage Curvo con Ganchos Laterales y Soporte",
    },
    "中古-大C（支架款）": {
        "code_prefix": "XW-WB12",
        "en": "Vintage C-Profile Sculpted Wood Stand Mirror",
        "si": "වින්ටේජ් C-හැඩැති ලී ආධාරක සම්පූර්ණ දිග කණ්ණාඩිය (Vintage C-Curve Stand Mirror)",
        "es": "Espejo Vintage Perfil C Escultural con Soporte",
    },
    "中古-雪糕（支架款）": {
        "code_prefix": "XW-WB13",
        "en": "Vintage Popsicle Arch Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් අයිස්ක්‍රීම් හැඩැති ලී ආධාරක කණ්ණාඩිය (Vintage Popsicle Arch Stand Mirror)",
        "es": "Espejo Vintage Arco Paleta de Pie con Soporte",
    },
    "中古-单边波浪（支架款）": {
        "code_prefix": "XW-WB14",
        "en": "Vintage Single-Side Wave Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් එක් පසෙක රැලි හැඩැති ආධාරක කණ්ණාඩිය (Vintage Single-Side Wave Mirror)",
        "es": "Espejo Vintage Onda Lateral Única con Soporte",
    },
    "中古-圆波浪（支架款）": {
        "code_prefix": "XW-WB15",
        "en": "Vintage Rounded Scallop Wave Wood Stand Mirror",
        "si": "වින්ටේජ් වටකුරු රැලි හැඩැති ලී ආධාරක කණ්ණාඩිය (Vintage Rounded Wave Stand Mirror)",
        "es": "Espejo Vintage Onda Redondeada de Pie con Soporte",
    },
    "中古-云朵（支架款）": {
        "code_prefix": "XW-MT08",
        "en": "Vintage Soft Cloud Wood-Backed Stand Mirror",
        "si": "වින්ටේජ් මෘදු වළාකුළු හැඩැති ආධාරක රූපලාවන්‍ය කණ්ණාඩිය (Vintage Soft Cloud Stand Mirror)",
        "es": "Espejo Vintage Nube Suave de Pie con Soporte",
    },

    # File 5: Metal / Aluminum Alloy / LED / Rolling Mirrors (金属穿衣镜)
    "塑钢圆角": {
        "code_prefix": "XW-MT01",
        "en": "Polymer-Steel Rounded-Corner Full-Length Mirror",
        "si": "ප්ලාස්ටික්-වානේ (Polymer-Steel) වටකුරු කොන් සහිත සම්පූර්ණ දිග කණ්ණාඩිය (Rounded Full-Length Mirror)",
        "es": "Espejo de Cuerpo Entero Esquinas Redondeadas de Acero Polimérico",
    },
    "拱形款": {
        "code_prefix": "XW-MT02",
        "en": "Aluminum Alloy Arch Frame Full-Length Mirror",
        "si": "ඇලුමිනියම් මිශ්‍ර ලෝහ ආරුක්කු රාමු සම්පූර්ණ දිග කණ්ණාඩිය (Aluminum Alloy Arch Mirror)",
        "es": "Espejo de Cuerpo Entero Diseño Arco de Aleación de Aluminio",
    },
    "圆角款": {
        "code_prefix": "XW-MT03",
        "en": "Aluminum Alloy Rounded-Corner Full-Length Mirror",
        "si": "ඇලුමිනියම් මිශ්‍ර ලෝහ වටකුරු කොන් සහිත සම්පූර්ණ දිග කණ්ණාඩිය (Aluminum Rounded Mirror)",
        "es": "Espejo de Cuerpo Entero Esquinas Redondeadas de Aleación de Aluminio",
    },
    "圆角灯镜": {
        "code_prefix": "XW-LED01",
        "en": "Smart Touch LED Lighted Rounded-Corner Full-Length Mirror",
        "si": "LED ආලෝකමත් ස්පර්ශක වටකුරු කොන් රූපලාවන්‍ය කණ්ණාඩිය (LED Smart Rounded Mirror)",
        "es": "Espejo Inteligente con Luz LED Táctil Esquinas Redondeadas",
    },
    "拱形灯镜": {
        "code_prefix": "XW-LED02",
        "en": "Smart Touch LED Lighted Arch Full-Length Mirror",
        "si": "LED ආලෝකමත් ස්පර්ශක ආරුක්කු හැඩැති රූපලාවන්‍ය කණ්ණාඩිය (LED Smart Arch Mirror)",
        "es": "Espejo Inteligente con Luz LED Táctil Diseño Arco",
    },
    "轮镜": {
        "code_prefix": "XW-MT04",
        "en": "360° Caster-Wheel Movable Full-Length Stand Mirror",
        "si": "රෝද සහිත පහසුවෙන් එහා මෙහා ගෙන යා හැකි සම්පූර්ණ දිග කණ්ණාඩිය (Movable Rolling Mirror)",
        "es": "Espejo de Cuerpo Entero Móvil con Ruedas Giratorias",
    },
    "波浪封边款": {
        "code_prefix": "XW-MT05",
        "en": "PU-Trimmed Wavy Contour Full-Length Stand Mirror",
        "si": "PU දාර සහිත රැලි හැඩැති සම්පූර්ණ දිග රූපලාවන්‍ය කණ්ණාඩිය (PU Wavy Edge Mirror)",
        "es": "Espejo de Cuerpo Entero Ondulado con Borde PU",
    },
    "脚印封边款": {
        "code_prefix": "XW-MT06",
        "en": "PU-Trimmed Footprint Silhouette Full-Length Mirror",
        "si": "PU දාර සහිත පා සලකුණු හැඩැති සම්පූර්ණ දිග කණ්ණාඩිය (PU Footprint Mirror)",
        "es": "Espejo de Cuerpo Entero Diseño Huella con Borde PU",
    },
}

MATERIAL_TRANSLATIONS = {
    "木板+绒布+海绵+铁": {
        "en": "Wood Board + Velvet Fabric + High-Density Sponge + Iron Stand",
        "si": "ලී පුවරුව + වෙල්වට් රෙදි + ස්පොන්ජ් + යකඩ ආධාරකය (Wood + Velvet + Sponge + Iron)",
        "es": "Tablero de Madera + Terciopelo + Esponja + Soporte de Hierro",
    },
    "木板+绒布+定型棉+铁": {
        "en": "Wood Board + Velvet Fabric + Molded Foam + Iron Stand",
        "si": "ලී පුවරුව + වෙල්වට් + හැඩගැන්වූ ෆෝම් + යකඩ ආධාරකය (Wood + Velvet + Molded Foam)",
        "es": "Tablero de Madera + Terciopelo + Espuma Moldeada + Hierro",
    },
    "木板+铁": {
        "en": "Solid Wood Backing Board + Iron Stand Bracket",
        "si": "ශක්තිමත් ලී පුවරුව + යකඩ ආධාරක රාමුව (Wood Board + Iron Bracket)",
        "es": "Tablero de Madera + Soporte Metálico de Hierro",
    },
    "塑钢+铁": {
        "en": "Polymer-Steel Frame + Iron Stand",
        "si": "ප්ලාස්ටික්-වානේ (Polymer-Steel) රාමුව + යකඩ ආධාරකය",
        "es": "Marco de Acero Polimérico + Soporte de Hierro",
    },
    "铝合金+铁": {
        "en": "Brushed Aluminum Alloy Frame + Iron Stand",
        "si": "ඇලුමිනියම් මිශ්‍ර ලෝහ (Aluminum Alloy) රාමුව + යකඩ ආධාරකය",
        "es": "Marco de Aleación de Aluminio + Soporte de Hierro",
    },
    "铝合金+LED灯+木板+铁": {
        "en": "Aluminum Alloy + Touch LED Strip + Wood Board + Iron Stand",
        "si": "ඇලුමිනියම් මිශ්‍ර ලෝහ + LED ආලෝක පද්ධතිය + ලී + යකඩ ආධාරකය",
        "es": "Aleación de Aluminio + Luz LED + Madera + Hierro",
    },
    "PVC+铁": {
        "en": "Durable PVC Frame + Iron Caster Stand",
        "si": "කල්පවතින PVC රාමුව + රෝද සහිත යකඩ ආධාරකය (PVC + Iron Caster Stand)",
        "es": "Marco de PVC Duradero + Base de Hierro con Ruedas",
    },
    "木板+PU条+铁": {
        "en": "Wood Board + Flexible PU Edge Trim + Iron Stand",
        "si": "ලී පුවරුව + නම්‍යශීලී PU දාර + යකඩ ආධාරකය (Wood + PU Trim + Iron)",
        "es": "Tablero de Madera + Borde PU + Soporte de Hierro",
    },
    "高清银镜+挂钩背板": {
        "en": "HD Float Silver Mirror + Wall Hanging Backing",
        "si": "උසස් තත්ත්වයේ HD රිදී කණ්ණාඩිය + බිත්ති එල්ලුම් පුවරුව (HD Silver Wall Mirror)",
        "es": "Espejo de Plata HD + Respaldo para Colgar en Pared",
    },
    "高密度生态木板+高清银镜+360°旋转底座": {
        "en": "High-Density Eco Wood + HD Silver Mirror + 360° Swivel Base",
        "si": "අධි-ඝනත්ව ලී පුවරුව + HD කණ්ණාඩිය + අංශක 360 කැරකෙන පාදම (360° Swivel Wood Base)",
        "es": "Madera Ecológica de Alta Densidad + Espejo HD + Base Giratoria 360°",
    },
}

CATEGORY_META = {
    "hanging-mirrors": {
        "id": "hanging-mirrors",
        "icon": "🪞",
        "en": "Wall & Hanging Mirrors",
        "si": "බිත්ති සහ එල්ලන කණ්ණාඩි (Wall Mirrors)",
        "zh": "挂钩家居镜",
        "es": "Espejos Colgantes de Pared",
    },
    "metal-mirrors": {
        "id": "metal-mirrors",
        "icon": "✨",
        "en": "Metal & Aluminum Mirrors",
        "si": "ලෝහ සහ ඇලුමිනියම් කණ්ණාඩි (Metal Mirrors)",
        "zh": "金属与铝合金穿衣镜",
        "es": "Espejos Metálicos y Aluminio",
    },
    "led-mirrors": {
        "id": "led-mirrors",
        "icon": "💡",
        "en": "LED Smart Mirrors",
        "si": "LED ස්මාර්ට් කණ්ණාඩි (LED Mirrors)",
        "zh": "LED智能带灯镜",
        "es": "Espejos Inteligentes LED",
    },
    "rotating-mirrors": {
        "id": "rotating-mirrors",
        "icon": "🔄",
        "en": "Rotating & Storage Mirrors",
        "si": "කැරකෙන සහ රාක්ක කණ්ණාඩි (Rotating Mirrors)",
        "zh": "旋转与书架收纳镜",
        "es": "Espejos Giratorios y Estantería",
    },
    "velvet-mirrors": {
        "id": "velvet-mirrors",
        "icon": "🛋️",
        "en": "Velvet Upholstered Mirrors",
        "si": "වෙල්වට් මෘදු රාමු කණ්ණාඩි (Velvet Mirrors)",
        "zh": "全包软包绒布镜",
        "es": "Espejos Tapizados en Terciopelo",
    },
    "vintage-mirrors": {
        "id": "vintage-mirrors",
        "icon": "🏛️",
        "en": "Vintage Stand Mirrors",
        "si": "වින්ටේජ් ආධාරක කණ්ණාඩි (Vintage Stand)",
        "zh": "中古异形支架板镜",
        "es": "Espejos Vintage de Pie",
    },
}


def col_to_idx(col_str):
    idx = 0
    for ch in col_str:
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def parse_cell_ref(ref):
    col = "".join(c for c in ref if c.isalpha())
    row = int("".join(c for c in ref if c.isdigit()))
    return row, col, col_to_idx(col)


def clean_dim_str(s):
    if not s:
        return ""
    s = str(s).strip()
    # Fix factory typo '40*l65' -> '40*165'
    s = re.sub(r"(?<=[*xX])l(?=\d)", "1", s)
    s = re.sub(r"[*xX]", "×", s)
    s = re.sub(r"\s+", "", s)
    if not s.lower().endswith("cm"):
        s = s + " cm"
    else:
        s = re.sub(r"(?i)cm$", " cm", s)
    return s


def compute_cbm_from_box(box_raw, fallback_cbm=None):
    if fallback_cbm is not None:
        try:
            v = float(fallback_cbm)
            if v > 0:
                return round(v, 4)
        except Exception:
            pass
    if not box_raw:
        return 0.05
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(box_raw))]
    if len(nums) >= 3:
        return round((nums[0] * nums[1] * nums[2]) / 1_000_000.0, 4)
    return 0.05


def parse_float(val, default=None):
    if val is None:
        return default
    s = str(val).strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", s)
    if m:
        try:
            return round(float(m.group(0)), 4)
        except Exception:
            return default
    return default


def parse_int(val, default=1):
    if val is None:
        return default
    m = re.search(r"\d+", str(val))
    return int(m.group(0)) if m else default


def translate_colors(raw_color):
    if not raw_color:
        return None
    cleaned = re.sub(r"^颜色[：:]\s*", "", str(raw_color).strip()).strip("，, ")
    if not cleaned:
        return None
    mapping = {
        "白": ("White", "සුදු (White)", "Blanco"),
        "胡桃": ("Walnut", "වෝල්නට් දුඹුරු (Walnut)", "Nogal"),
        "原木": ("Natural Oak", "ස්වභාවික ලී වර්ණය (Natural Wood)", "Madera Natural"),
        "灰": ("Grey", "අළු (Grey)", "Gris"),
        "黑": ("Black", "කළු (Black)", "Negro"),
    }
    parts = [p.strip() for p in re.split(r"[，,/、\s]+", cleaned) if p.strip()]
    en_l, si_l, es_l = [], [], []
    for pt in parts:
        if pt in mapping:
            en_l.append(mapping[pt][0])
            si_l.append(mapping[pt][1])
            es_l.append(mapping[pt][2])
        else:
            en_l.append(pt)
            si_l.append(pt)
            es_l.append(pt)
    return {
        "zh": " / ".join(parts),
        "en": " / ".join(en_l),
        "si": " / ".join(si_l),
        "es": " / ".join(es_l),
    }


def classify_category(zh_name, sheet_label, material_zh):
    if "挂钩" in sheet_label or any(zh_name.startswith(p) for p in ("25", "26")):
        return "hanging-mirrors"
    if "灯镜" in zh_name or "LED" in material_zh:
        return "led-mirrors"
    if "旋转" in sheet_label or any(k in zh_name for k in ("旋转", "洞洞", "书架", "推拉镜", "双面熊")):
        return "rotating-mirrors"
    if "绒布" in zh_name or "绒布" in material_zh:
        return "velvet-mirrors"
    if "中古" in zh_name:
        return "vintage-mirrors"
    return "metal-mirrors"


class ImageStore:
    """
    Deduplicates extracted binary images by SHA-256 hash and writes:
      - website/images/pXXX_t.webp (max side 360px, quality 82)
      - website/images/pXXX_l.webp (max side 1100px, quality 85)
    """
    def __init__(self, images_dir):
        self.images_dir = images_dir
        os.makedirs(self.images_dir, exist_ok=True)
        self.hash_to_paths = {}
        self.counter = 0

    def save_image_bytes(self, raw_bytes):
        if not raw_bytes:
            return None, None
        h = hashlib.sha256(raw_bytes).hexdigest()
        if h in self.hash_to_paths:
            return self.hash_to_paths[h]

        self.counter += 1
        img_id = f"p{self.counter:03d}"
        thumb_rel = f"images/{img_id}_t.webp"
        large_rel = f"images/{img_id}_l.webp"
        thumb_abs = os.path.join(self.images_dir, f"{img_id}_t.webp")
        large_abs = os.path.join(self.images_dir, f"{img_id}_l.webp")

        with Image.open(io.BytesIO(raw_bytes)) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            elif im.mode == "RGBA":
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3])
                im = bg

            # Large high-res (max side 1100px, quality 85)
            im_large = im.copy()
            im_large.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
            im_large.save(large_abs, "WEBP", quality=85, method=4)

            # Thumbnail (max side 360px, quality 82)
            im_thumb = im.copy()
            im_thumb.thumbnail((360, 360), Image.Resampling.LANCZOS)
            im_thumb.save(thumb_abs, "WEBP", quality=82, method=4)

        self.hash_to_paths[h] = (thumb_rel, large_rel)
        return thumb_rel, large_rel


def extract_wps_cellimages(z):
    """
    Parses WPS Office xl/cellimages.xml and xl/_rels/cellimages.xml.rels
    for in-cell =DISPIMG("ID_...", 1) formulas.
    Returns dict mapping image_id (e.g. 'ID_XXXX') -> raw image bytes.
    """
    namelist = z.namelist()
    if "xl/cellimages.xml" not in namelist:
        return {}
    rel_map = {}
    if "xl/_rels/cellimages.xml.rels" in namelist:
        rels_root = ET.fromstring(z.read("xl/_rels/cellimages.xml.rels"))
        for rel in rels_root:
            r_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("./")
            rel_map[r_id] = target

    id_to_bytes = {}
    ci_root = ET.fromstring(z.read("xl/cellimages.xml"))
    for pic in ci_root.findall(".//xdr:pic", NS):
        cNvPr = pic.find(".//xdr:cNvPr", NS)
        blip = pic.find(".//a:blip", NS)
        if cNvPr is not None and blip is not None:
            name = cNvPr.attrib.get("name", "")
            embed = blip.attrib.get(R_EMBED, "")
            media_path = rel_map.get(embed, "")
            if name and media_path in namelist:
                id_to_bytes[name] = z.read(media_path)
    return id_to_bytes


def extract_sheet_drawings(z, sheet_target):
    """
    Extracts OpenXML floating drawing anchors (twoCellAnchor / oneCellAnchor)
    for a given worksheet.
    Returns list of dicts: { 'from_row': int (1-based), 'to_row': int (1-based),
                             'from_col': int (0-based), 'to_col': int (0-based),
                             'bytes': bytes }
    """
    namelist = z.namelist()
    sheet_dir = os.path.dirname(sheet_target)
    sheet_base = os.path.basename(sheet_target)
    rels_path = f"{sheet_dir}/_rels/{sheet_base}.rels"
    if rels_path not in namelist:
        return []

    anchors = []
    s_rels = ET.fromstring(z.read(rels_path))
    for rel in s_rels:
        if not rel.attrib.get("Type", "").endswith("/drawing"):
            continue
        dr_target = rel.attrib.get("Target", "")
        dr_path = "xl/drawings/" + os.path.basename(dr_target)
        dr_rels_path = "xl/drawings/_rels/" + os.path.basename(dr_target) + ".rels"
        if dr_path not in namelist:
            continue

        dr_rel_map = {}
        if dr_rels_path in namelist:
            for drel in ET.fromstring(z.read(dr_rels_path)):
                t = drel.attrib.get("Target", "")
                media_p = "xl/media/" + os.path.basename(t)
                dr_rel_map[drel.attrib.get("Id")] = media_p

        dr_root = ET.fromstring(z.read(dr_path))
        for tag in ("twoCellAnchor", "oneCellAnchor"):
            for anc in dr_root.findall(f"xdr:{tag}", NS):
                fr = anc.find("xdr:from", NS)
                to = anc.find("xdr:to", NS)
                blip = anc.find(".//a:blip", NS)
                if fr is None or blip is None:
                    continue
                fc = int(fr.find("xdr:col", NS).text)
                fr_r = int(fr.find("xdr:row", NS).text) + 1
                tc = int(to.find("xdr:col", NS).text) if to is not None else fc
                tr_r = int(to.find("xdr:row", NS).text) + 1 if to is not None else fr_r
                embed = blip.attrib.get(R_EMBED, "")
                media_p = dr_rel_map.get(embed, "")
                if media_p in namelist:
                    anchors.append({
                        "from_row": fr_r,
                        "to_row": max(fr_r, tr_r),
                        "from_col": fc,
                        "to_col": max(fc, tc),
                        "bytes": z.read(media_p),
                        "media_path": media_p,
                    })
    return anchors


def read_sheet_cells_and_merges(z, sheet_target, shared_strings, wps_images):
    """
    Reads all cells (values + DISPIMG formulas) and merged cell ranges from a worksheet.
    """
    root = ET.fromstring(z.read(sheet_target))
    rows_dict = {}
    dispimg_by_row_col = {}

    for r in root.findall(".//main:row", NS):
        r_num = int(r.attrib.get("r", 0))
        row_vals = {}
        for c in r.findall("main:c", NS):
            ref = c.attrib.get("r", "")
            _, col_let, col_idx = parse_cell_ref(ref)
            c_type = c.attrib.get("t")
            v_el = c.find("main:v", NS)
            f_el = c.find("main:f", NS)
            is_el = c.find("main:is", NS)

            val = None
            if c_type == "s" and v_el is not None and v_el.text is not None:
                val = shared_strings[int(v_el.text)]
            elif c_type == "inlineStr" and is_el is not None:
                val = "".join(t.text or "" for t in is_el.findall(".//main:t", NS))
            elif v_el is not None and v_el.text is not None:
                val = v_el.text

            # Check WPS =DISPIMG("ID_...", 1) in formula or string value
            formula_txt = (f_el.text or "") if f_el is not None else ""
            check_str = f"{formula_txt} {val or ''}"
            m_disp = re.search(r'DISPIMG\(\s*"([^"]+)"', check_str, re.IGNORECASE)
            if m_disp:
                img_id = m_disp.group(1)
                if img_id in wps_images:
                    dispimg_by_row_col[(r_num, col_idx)] = wps_images[img_id]

            if val is not None:
                row_vals[col_let] = str(val).strip()
        if row_vals:
            rows_dict[r_num] = row_vals

    merges = []
    for mc in root.findall(".//main:mergeCell", NS):
        ref = mc.attrib.get("ref", "")
        if ":" in ref:
            p1, p2 = ref.split(":")
            r1, c1, ci1 = parse_cell_ref(p1)
            r2, c2, ci2 = parse_cell_ref(p2)
            merges.append((min(r1, r2), max(r1, r2), min(ci1, ci2), max(ci1, ci2), c1))

    return rows_dict, merges, dispimg_by_row_col


def find_image_for_row(row_num, col_range, anchors, dispimg_by_row_col, merges):
    """
    Finds the best matching image bytes for (row_num, col_range) from either
    WPS DISPIMG cells or OpenXML drawing anchors (including merged cell propagation).
    """
    min_c, max_c = col_range
    # 1. Check direct DISPIMG in row_num
    for (r, c), img_bytes in dispimg_by_row_col.items():
        if r == row_num and min_c <= c <= max_c:
            return img_bytes

    # 2. Check if row_num is inside a merged cell in col_range and check DISPIMG/anchors covering that merge
    eff_r_start, eff_r_end = row_num, row_num
    for r1, r2, c1, c2, _ in merges:
        if r1 <= row_num <= r2 and not (c2 < min_c or c1 > max_c):
            eff_r_start = min(eff_r_start, r1)
            eff_r_end = max(eff_r_end, r2)

    for (r, c), img_bytes in dispimg_by_row_col.items():
        if eff_r_start <= r <= eff_r_end and min_c <= c <= max_c:
            return img_bytes

    # 3. Check drawing anchors overlapping [eff_r_start, eff_r_end] and [min_c, max_c]
    best_anc = None
    best_overlap = -1
    for anc in anchors:
        if anc["to_col"] < min_c or anc["from_col"] > max_c:
            continue
        # Note: sometimes an anchor ends on the boundary row of the next block;
        # prefer anchors whose from_row is inside [eff_r_start - 1, eff_r_end]
        ov_start = max(eff_r_start, anc["from_row"])
        ov_end = min(eff_r_end, anc["to_row"])
        overlap = ov_end - ov_start + 1
        if overlap >= 1:
            # Prefer anchor whose from_row is closest to eff_r_start
            score = overlap * 100 - abs(anc["from_row"] - eff_r_start)
            if score > best_overlap:
                best_overlap = score
                best_anc = anc

    if best_anc is not None:
        return best_anc["bytes"]

    # 4. Fallback: nearest anchor in col_range within 3 rows
    nearest = None
    nearest_dist = 999
    for anc in anchors:
        if anc["to_col"] < min_c or anc["from_col"] > max_c:
            continue
        dist = min(abs(anc["from_row"] - eff_r_start), abs(anc["to_row"] - eff_r_end))
        if dist <= 3 and dist < nearest_dist:
            nearest_dist = dist
            nearest = anc
    return nearest["bytes"] if nearest else None


def build_product_record(
    raw_zh_name,
    sheet_label,
    size_raw,
    box_raw,
    price_rmb,
    pcs_per_carton,
    kg_val,
    cbm_val,
    thickness_raw="",
    material_raw="",
    package_raw="",
    colors_raw="",
    price_teddy=None,
    price_rabbit=None,
    price_2pack=None,
    kg_2pack=None,
    thumb_path="",
    large_path="",
    seq_in_model=1,
    code_override=None,
):
    raw_zh_key = raw_zh_name.strip()
    trans = PRODUCT_TRANSLATIONS.get(raw_zh_key, {})

    zh_Display = trans.get("zh_clean", raw_zh_key)
    en_base = trans.get("en", raw_zh_key)
    si_base = trans.get("si", f"{raw_zh_key} කණ්ණාඩිය ({en_base})")
    es_base = trans.get("es", en_base)
    code_prefix = code_override or trans.get("code_prefix", f"XW-{seq_in_model:03d}")

    size_clean = clean_dim_str(size_raw)
    size_compact = re.sub(r"\s*cm$", "", size_clean, flags=re.I).replace("×", "x")
    size_digits = re.sub(r"[^0-9]", "", size_compact)

    if code_override:
        item_code = code_override
    elif size_digits:
        item_code = f"{code_prefix}-{size_digits}"
    else:
        item_code = f"{code_prefix}-{seq_in_model:02d}"

    box_clean = clean_dim_str(box_raw) if box_raw else ""
    cbm_final = compute_cbm_from_box(box_raw, cbm_val)

    # Material translation
    mat_key = material_raw.strip() if material_raw else ""
    if not mat_key:
        if "挂钩" in sheet_label or "挂镜" in zh_Display:
            mat_key = "高清银镜+挂钩背板"
        elif "旋转" in sheet_label:
            mat_key = "高密度生态木板+高清银镜+360°旋转底座"
        else:
            mat_key = "木板+铁"
    mat_tr = MATERIAL_TRANSLATIONS.get(mat_key, {
        "en": mat_key,
        "si": mat_key,
        "es": mat_key,
    })

    # Colors translation
    col_tr = translate_colors(colors_raw)

    # Variant strings in all 4 languages
    var_parts_en = []
    var_parts_si = []
    var_parts_zh = []
    var_parts_es = []

    if size_clean:
        var_parts_en.append(f"Size: {size_clean}")
        var_parts_si.append(f"ප්‍රමාණය: {size_clean}")
        var_parts_zh.append(f"尺寸: {size_clean}")
        var_parts_es.append(f"Tamaño: {size_clean}")

    if thickness_raw:
        var_parts_en.append(f"Glass: {thickness_raw}")
        var_parts_si.append(f"වීදුරු ඝනකම: {thickness_raw}")
        var_parts_zh.append(f"镜片: {thickness_raw}")
        var_parts_es.append(f"Vidrio: {thickness_raw}")

    if price_teddy and price_rabbit:
        var_parts_en.append(f"Velvet (Teddy ¥{price_teddy:g} / Rabbit Fur ¥{price_rabbit:g})")
        var_parts_si.append(f"වෙල්වට් (Teddy ¥{price_teddy:g} / Rabbit ¥{price_rabbit:g})")
        var_parts_zh.append(f"绒布 (泰迪绒 ¥{price_teddy:g} / 兔毛 ¥{price_rabbit:g})")
        var_parts_es.append(f"Terciopelo (Teddy ¥{price_teddy:g} / Pelo Conejo ¥{price_rabbit:g})")
    elif price_2pack:
        var_parts_en.append(f"1pc Pack (2-Pack: ¥{price_2pack:g}/pc)")
        var_parts_si.append(f"තනි ඇසුරුම (කෑලි 2 ඇසුරුම: ¥{price_2pack:g}/pc)")
        var_parts_zh.append(f"单件装 (2件装单价: ¥{price_2pack:g})")
        var_parts_es.append(f"1 ud/caja (Pack de 2: ¥{price_2pack:g}/ud)")
    elif pcs_per_carton > 1:
        var_parts_en.append(f"{pcs_per_carton} pcs/carton · Bubble Packed")
        var_parts_si.append(f"පෙට්ටියකට කෑලි {pcs_per_carton} · ආරක්ෂිත බබල් ඇසුරුම")
        var_parts_zh.append(f"{pcs_per_carton}个/箱 · 独立气泡袋")
        var_parts_es.append(f"{pcs_per_carton} uds/caja · Bolsa de Burbujas")
    elif col_tr:
        var_parts_en.append(f"Colors: {col_tr['en']}")
        var_parts_si.append(f"වර්ණ: {col_tr['si']}")
        var_parts_zh.append(f"颜色: {col_tr['zh']}")
        var_parts_es.append(f"Colores: {col_tr['es']}")

    variant_en = " · ".join(var_parts_en) if var_parts_en else "Standard"
    variant_si = " · ".join(var_parts_si) if var_parts_si else "සම්මත මාදිලිය (Standard)"
    variant_zh = " · ".join(var_parts_zh) if var_parts_zh else "标准款"
    variant_es = " · ".join(var_parts_es) if var_parts_es else "Estándar"

    cat_id = classify_category(raw_zh_key, sheet_label, mat_key)

    # Include size in display names so cards are immediately distinguishable
    size_tag = f" ({size_clean})" if size_clean else ""
    full_zh = f"{zh_Display}{size_tag}"
    full_en = f"{en_base}{size_tag}"
    full_si = f"{si_base}{size_tag}"
    full_es = f"{es_base}{size_tag}"

    return {
        "code": item_code,
        "modelNameZh": zh_Display,
        "zh": full_zh,
        "en": full_en,
        "si": full_si,
        "es": full_es,
        "variant": variant_en,
        "variantEn": variant_en,
        "variantSi": variant_si,
        "variantZh": variant_zh,
        "variantEs": variant_es,
        "variantByLang": {
            "en": variant_en,
            "si": variant_si,
            "zh": variant_zh,
            "es": variant_es,
        },
        "category": cat_id,
        "sheet": sheet_label,
        "pcsPerCarton": int(pcs_per_carton),
        "price": round(float(price_rmb), 2),
        "priceTeddy": round(float(price_teddy), 2) if price_teddy else None,
        "priceRabbit": round(float(price_rabbit), 2) if price_rabbit else None,
        "price2Pack": round(float(price_2pack), 2) if price_2pack else None,
        "kg2Pack": round(float(kg_2pack), 2) if kg_2pack else None,
        "cbm": cbm_final,
        "kg": round(float(kg_val), 2) if kg_val is not None else None,
        "box": box_clean,
        "size": size_clean,
        "thickness": thickness_raw or "3mm HD",
        "material": mat_tr["en"],
        "materialByLang": {
            "en": mat_tr["en"],
            "si": mat_tr["si"],
            "zh": mat_key,
            "es": mat_tr["es"],
        },
        "colorsByLang": col_tr,
        "packageType": package_raw or "5层牛皮纸箱",
        "thumb": thumb_path,
        "large": large_path,
    }


def parse_rotating_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label):
    """
    Parses the 2-column block layout of Copy of XW旋转镜子报价单2026.xlsx (Sheet: 旋转镜).
    Left block: Image in cols A-C (0..2), Title & Table in cols D-H (3..7).
    Right block: Image in cols I-K (8..10), Title & Table in cols L-P (11..15).
    """
    products = []
    max_r = max(rows_dict.keys()) if rows_dict else 0

    # Side definitions: (title_col, size_col, box_col, kg_col, cbm_col, price_col, color_col, img_col_range, side_tag)
    sides = [
        ("D", "D", "E", "F", "G", "H", "A", (0, 2), "L"),
        ("L", "L", "M", "N", "O", "P", "I", (8, 10), "R"),
    ]

    block_counter = 0
    for r_num in range(1, max_r + 1):
        row = rows_dict.get(r_num, {})
        for (t_col, sz_col, bx_col, kg_col, cbm_col, pr_col, clr_col, img_cols, side_tag) in sides:
            val_t = row.get(t_col, "")
            next_row = rows_dict.get(r_num + 1, {})
            next_hdr = next_row.get(sz_col, "").upper()
            if val_t and next_hdr in ("SIZE", "尺寸"):
                # Found a product block!
                block_counter += 1
                raw_zh_name = val_t.strip()

                # Find color note in clr_col within [r_num, r_num + 12]
                colors_raw = ""
                for cr in range(r_num, r_num + 13):
                    c_txt = rows_dict.get(cr, {}).get(clr_col, "")
                    if "颜色" in c_txt:
                        colors_raw = c_txt
                        break

                # Find image anchored near r_num in img_cols
                img_bytes = None
                best_dist = 999
                for anc in anchors:
                    if anc["to_col"] < img_cols[0] or anc["from_col"] > img_cols[1]:
                        continue
                    dist = abs(anc["from_row"] - r_num)
                    if dist <= 4 and dist < best_dist:
                        best_dist = dist
                        img_bytes = anc["bytes"]

                thumb_p, large_p = img_store.save_image_bytes(img_bytes) if img_bytes else ("", "")

                # Read spec rows starting at r_num + 2
                seq = 0
                for sr in range(r_num + 2, r_num + 12):
                    srow = rows_dict.get(sr, {})
                    sz = srow.get(sz_col, "")
                    pr = parse_float(srow.get(pr_col))
                    if not sz or pr is None:
                        break
                    seq += 1
                    bx = srow.get(bx_col, "")
                    kg = parse_float(srow.get(kg_col))
                    cbm = parse_float(srow.get(cbm_col))

                    trans = PRODUCT_TRANSLATIONS.get(raw_zh_name, {})
                    base_prefix = trans.get("code_prefix", f"XW-RT{block_counter:02d}")
                    size_digits = re.sub(r"[^0-9]", "", clean_dim_str(sz))
                    code_ov = f"{base_prefix}B{block_counter:02d}-{size_digits}"

                    prod = build_product_record(
                        raw_zh_name=raw_zh_name,
                        sheet_label=sheet_label,
                        size_raw=sz,
                        box_raw=bx,
                        price_rmb=pr,
                        pcs_per_carton=1,
                        kg_val=kg,
                        cbm_val=cbm,
                        thickness_raw="3mm HD",
                        material_raw="高密度生态木板+高清银镜+360°旋转底座",
                        package_raw="5层加厚牛皮纸箱+防震泡沫",
                        colors_raw=colors_raw,
                        thumb_path=thumb_p,
                        large_path=large_p,
                        seq_in_model=seq,
                        code_override=code_ov,
                    )
                    products.append(prod)

    return products


def parse_hanging_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label):
    """
    Parses Copy of XW挂钩家居镜价格表.xlsx (Sheet: 报价表).
    Row 2: {'A': '产品图', 'B': '货号', 'C': '规格', 'D': '装箱数', 'E': '包装方式', 'F': '价格', 'G': '体积（CM）', 'H': '重量'}
    """
    products = []
    for r_num in sorted(rows_dict.keys()):
        if r_num <= 2:
            continue
        row = rows_dict[r_num]
        raw_name = row.get("B", "").strip()
        price_val = parse_float(row.get("F"))
        if not raw_name or price_val is None:
            continue

        size_raw = row.get("C", "")
        pcs_val = parse_int(row.get("D"), default=1)
        pkg_raw = row.get("E", "独立气泡袋")
        box_raw = row.get("G", "")
        kg_val = parse_float(row.get("H"))

        img_bytes = find_image_for_row(r_num, (0, 1), anchors, dispimg_by_row_col, merges)
        thumb_p, large_p = img_store.save_image_bytes(img_bytes) if img_bytes else ("", "")

        trans = PRODUCT_TRANSLATIONS.get(raw_name, {})
        code_ov = trans.get("code_prefix", f"XW-HM{r_num:02d}")

        prod = build_product_record(
            raw_zh_name=raw_name,
            sheet_label=sheet_label,
            size_raw=size_raw,
            box_raw=box_raw,
            price_rmb=price_val,
            pcs_per_carton=pcs_val,
            kg_val=kg_val,
            cbm_val=None,
            thickness_raw="2mm HD",
            material_raw="高清银镜+挂钩背板",
            package_raw=pkg_raw,
            thumb_path=thumb_p,
            large_path=large_p,
            seq_in_model=r_num - 2,
            code_override=code_ov,
        )
        products.append(prod)
    return products


def parse_standard_mirror_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label, file_tag):
    """
    Parses standard row tables with merged cells in Column A / B:
    - Copy of XW全包软包穿衣镜报价.xlsx (file_tag='VP')
    - Copy of XW板镜报价单.xlsx (file_tag='WB')
    - Copy of XW金属穿衣镜报价单.xlsx (file_tag='MT')
    """
    products = []
    # Build merged cell lookup for column B (description) and column A (image)
    col_b_merge_val = {}
    for r1, r2, c1, c2, _ in merges:
        if c1 <= 1 <= c2:
            top_val = rows_dict.get(r1, {}).get("B", "")
            if top_val:
                for rr in range(r1, r2 + 1):
                    col_b_merge_val[rr] = top_val

    last_desc = ""
    seq_counter = 0

    for r_num in sorted(rows_dict.keys()):
        row = rows_dict[r_num]
        # Skip header rows or section notes
        b_val = row.get("B", "") or col_b_merge_val.get(r_num, "")
        if b_val in ("description", "des", "名称", "货号"):
            continue
        if row.get("A", "") in ("picture", "图片", "产品图"):
            continue

        size_raw = row.get("E", "")
        box_raw = row.get("F", "")
        if not size_raw and not box_raw:
            continue

        if b_val:
            last_desc = b_val

        raw_zh_name = b_val or last_desc
        if not raw_zh_name:
            continue

        thick_raw = row.get("C", "")
        mat_raw = row.get("D", "")

        # Determine columns based on file_tag
        if file_tag == "VP":
            # G: velvet price, H: weight, I: package, J: 泰迪绒单价, K: Rabbit hair price
            price_val = parse_float(row.get("G"))
            kg_val = parse_float(row.get("H"))
            pkg_raw = row.get("I", "5层牛皮纸箱")
            cbm_val = None
            price_teddy = parse_float(row.get("J"))
            price_rabbit = parse_float(row.get("K"))
            price_2pack = None
            kg_2pack = None
        else:
            # G: CBM/CBA, H: price, I: weight, J: package, K: price of 2 packing, L: weight
            cbm_val = parse_float(row.get("G"))
            price_val = parse_float(row.get("H"))
            kg_val = parse_float(row.get("I"))
            pkg_raw = row.get("J", "5层牛皮纸箱")
            price_teddy = None
            price_rabbit = None
            price_2pack = parse_float(row.get("K"))
            kg_2pack = parse_float(row.get("L"))

        if price_val is None:
            continue

        seq_counter += 1
        img_bytes = find_image_for_row(r_num, (0, 1), anchors, dispimg_by_row_col, merges)
        thumb_p, large_p = img_store.save_image_bytes(img_bytes) if img_bytes else ("", "")

        trans = PRODUCT_TRANSLATIONS.get(raw_zh_name.strip(), {})
        base_prefix = trans.get("code_prefix", f"XW-{file_tag}{seq_counter:02d}")
        if file_tag == "MT" and base_prefix.startswith("XW-WB"):
            base_prefix = base_prefix.replace("XW-WB", "XW-MTW")
        size_digits = re.sub(r"[^0-9]", "", clean_dim_str(size_raw))
        code_ov = f"{base_prefix}-{size_digits}"

        prod = build_product_record(
            raw_zh_name=raw_zh_name,
            sheet_label=sheet_label,
            size_raw=size_raw,
            box_raw=box_raw,
            price_rmb=price_val,
            pcs_per_carton=1,
            kg_val=kg_val,
            cbm_val=cbm_val,
            thickness_raw=thick_raw,
            material_raw=mat_raw,
            package_raw=pkg_raw,
            price_teddy=price_teddy,
            price_rabbit=price_rabbit,
            price_2pack=price_2pack,
            kg_2pack=kg_2pack,
            thumb_path=thumb_p,
            large_path=large_p,
            seq_in_model=seq_counter,
            code_override=code_ov,
        )
        products.append(prod)

    return products


def process_xlsx_file(xlsx_path, img_store):
    fname = os.path.basename(xlsx_path)
    print(f"Processing workbook: {fname}")
    products = []

    with zipfile.ZipFile(xlsx_path, "r") as z:
        namelist = z.namelist()
        shared_strings = []
        if "xl/sharedStrings.xml" in namelist:
            ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("main:si", NS):
                shared_strings.append("".join(t.text or "" for t in si.findall(".//main:t", NS)))

        wps_images = extract_wps_cellimages(z)

        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        wb_rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in wb_rels}

        for sheet in wb_root.findall(".//main:sheet", NS):
            s_name = sheet.attrib.get("name", "Sheet1")
            r_id = sheet.attrib.get(R_ID, "")
            target = rel_map.get(r_id, "")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            if target not in namelist:
                continue

            rows_dict, merges, dispimg_by_row_col = read_sheet_cells_and_merges(
                z, target, shared_strings, wps_images
            )
            if not rows_dict:
                continue

            anchors = extract_sheet_drawings(z, target)

            if "旋转" in fname or "旋转" in s_name:
                sheet_label = "旋转与收纳镜系列 (Rotating & Storage Series)"
                prods = parse_rotating_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label)
            elif "挂钩" in fname or "报价表" in s_name:
                sheet_label = "挂钩家居镜系列 (Wall Hanging Mirror Series)"
                prods = parse_hanging_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label)
            elif "软包" in fname or "全包" in fname:
                sheet_label = "全包软包穿衣镜系列 (Velvet Upholstered Mirror Series)"
                prods = parse_standard_mirror_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label, "VP")
            elif "金属" in fname:
                sheet_label = "金属与智能灯镜系列 (Metal & Smart LED Mirror Series)"
                prods = parse_standard_mirror_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label, "MT")
            else:
                sheet_label = "中古支架板镜系列 (Vintage Wood-Stand Mirror Series)"
                prods = parse_standard_mirror_sheet(rows_dict, merges, anchors, dispimg_by_row_col, img_store, sheet_label, "WB")

            print(f"  -> Sheet '{s_name}': extracted {len(prods)} products")
            products.extend(prods)

    return products


def build_catalog(xlsx_files):
    images_dir = os.path.join(WEBSITE_DIR, "images")
    data_dir = os.path.join(WEBSITE_DIR, "data")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    img_store = ImageStore(images_dir)
    all_products = []

    for fpath in xlsx_files:
        prods = process_xlsx_file(fpath, img_store)
        all_products.extend(prods)

    # Ensure unique IDs and unique codes, and build multi-image galleries per category/series
    seen_codes = {}
    cat_images = {}
    for p in all_products:
        cat = p["category"]
        if p["thumb"] and p["large"]:
            cat_images.setdefault(cat, [])
            pair = {"thumb": p["thumb"], "large": p["large"], "label": p["modelNameZh"]}
            if not any(x["thumb"] == pair["thumb"] for x in cat_images[cat]):
                cat_images[cat].append(pair)

    for idx, p in enumerate(all_products, start=1):
        p["id"] = idx
        c = p["code"]
        if c in seen_codes:
            seen_codes[c] += 1
            p["code"] = f"{c}-{seen_codes[c]}"
        else:
            seen_codes[c] = 1

        # Build gallery images list (product's own image first, plus up to 3 related model views from same category)
        gallery = []
        if p["thumb"] and p["large"]:
            gallery.append({"thumb": p["thumb"], "large": p["large"], "label": p["en"]})
        for rel_img in cat_images.get(p["category"], []):
            if rel_img["thumb"] != p["thumb"] and len(gallery) < 4:
                gallery.append(rel_img)
        p["images"] = gallery

    # Evaluate SL-WPI 100-Point Sea Cargo Winning Scores
    score_all_products(all_products)

    # Build category list with counts
    cat_counts = {}
    for p in all_products:
        cat_counts[p["category"]] = cat_counts.get(p["category"], 0) + 1

    categories_list = []
    for cat_id, meta in CATEGORY_META.items():
        if cat_counts.get(cat_id, 0) > 0:
            entry = dict(meta)
            entry["count"] = cat_counts[cat_id]
            categories_list.append(entry)

    catalog = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "currency": "RMB",
        "exchangeRates": {
            "USD": 7.15,
            "LKR": 43.50,
        },
        "totalProducts": len(all_products),
        "uniqueImages": img_store.counter,
        "categories": categories_list,
        "products": all_products,
    }

    out_path = os.path.join(data_dir, "products.js")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("window.CATALOG = " + json.dumps(catalog, ensure_ascii=False, indent=2) + ";\n")

    print(f"\nBuild complete! Total products: {len(all_products)}, Unique WebP image pairs: {img_store.counter}")
    print(f"Output written to: {out_path}")


def main():
    cli_files = [a for a in sys.argv[1:] if a.lower().endswith(".xlsx") and os.path.exists(a)]
    if cli_files:
        xlsx_files = sorted(cli_files)
    else:
        xlsx_files = sorted(glob.glob(os.path.join(ROOT_DIR, "*.xlsx")))
    if not xlsx_files:
        raise FileNotFoundError(f"No .xlsx files found in {ROOT_DIR}")
    build_catalog(xlsx_files)


if __name__ == "__main__":
    main()
