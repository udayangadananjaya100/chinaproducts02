#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sri Lanka Winning Product Index (SL-WPI — 100-Point Sea Cargo Model)
Evaluates every product on a 100-point scale across 4 pillars (0-25 pts each):
  1. Freight & Sea Cargo Efficiency (0-25 pts)
  2. Profit Margin & SL Retail Sweet Spot (0-25 pts)
  3. Local Consumer Demand & Viral Appeal (0-25 pts)
  4. Operational & COD Return Risk (0-25 pts)

Guarantees:
  freight.score + margin.score + demand.score + risk.score == winScore (100% exact)
  winRate == f"{winScore}%"
  winTier in ('mega', 'strong', 'niche', 'low')
  Dynamic, context-accurate explanations in en, si, zh, es for every pillar & winReason.
"""

import json
import os
import re

DEFAULT_LKR_RATE = 43.50
DEFAULT_USD_RATE = 7.15

TIER_META = {
    "mega": {
        "en": "🏆 Mega Winner",
        "si": "🏆 සුපිරි ජයග්‍රාහී භාණ්ඩය (Mega Winner)",
        "zh": "🏆 超级爆款 (Mega Winner)",
        "es": "🏆 Mega Ganador"
    },
    "strong": {
        "en": "⭐ Strong Winner",
        "si": "⭐ ඉහළ විකුණුම් හැකියාවක් ඇති (Strong Winner)",
        "zh": "⭐ 强力爆款 (Strong Winner)",
        "es": "⭐ Ganador Fuerte"
    },
    "niche": {
        "en": "⚖️ Niche Product",
        "si": "⚖️ විශේෂිත වෙළඳපොළ භාණ්ඩය (Niche Product)",
        "zh": "⚖️ 细分市场产品 (Niche Product)",
        "es": "⚖️ Producto de Nicho"
    },
    "low": {
        "en": "⚠️ Low Feasibility",
        "si": "⚠️ අඩු යෝග්‍යතාවයක් ඇති (Low Feasibility)",
        "zh": "⚠️ 低可行性 (Low Feasibility)",
        "es": "⚠️ Baja Viabilidad"
    }
}


def compute_freight_pillar(p):
    """
    1. Freight & Sea Cargo Efficiency (0-25 pts)
    Based on unit volume (cbm / pcsPerCarton) and unit weight (kg / pcsPerCarton).
    Ultra-compact items (<= 0.0008 m³/pc, <= 0.35 kg/pc) score up to 25/25.
    """
    pcs = max(1, int(p.get("pcsPerCarton") or 1))
    cbm = float(p.get("cbm") or 0.05)
    kg_val = p.get("kg")
    kg = float(kg_val) if (kg_val is not None and kg_val > 0) else (cbm * 180.0)

    unit_cbm = cbm / pcs
    unit_kg = kg / pcs

    # Score calculation (0-25)
    if unit_cbm <= 0.0008 and unit_kg <= 0.35:
        score = 25
    elif unit_cbm <= 0.0012 and unit_kg <= 0.45:
        score = 24
    elif unit_cbm <= 0.0020 and unit_kg <= 0.75:
        score = 23
    elif unit_cbm <= 0.0032 and unit_kg <= 1.20:
        score = 21
    elif unit_cbm <= 0.0050 and unit_kg <= 2.00:
        score = 20
    elif unit_cbm <= 0.0160 and unit_kg <= 3.50:
        score = 19
    elif unit_cbm <= 0.0285 and unit_kg <= 4.50:
        score = 18
    elif unit_cbm <= 0.0360 and unit_kg <= 5.50:
        score = 17
    elif unit_cbm <= 0.0525 and unit_kg <= 6.50:
        score = 15
    elif unit_cbm <= 0.0600 and unit_kg <= 11.50:
        score = 13
    elif unit_cbm <= 0.0700 and unit_kg <= 14.50:
        score = 11
    elif unit_cbm <= 0.0800 and unit_kg <= 17.50:
        score = 9
    elif unit_cbm <= 0.0950 and unit_kg <= 20.00:
        score = 7
    else:
        score = 5

    # Bonus +1 if 2-pack option exists and reduces unit CBM/weight
    if p.get("price2Pack") and score < 25:
        score = min(25, score + 1)

    score = max(0, min(25, int(score)))

    # Dynamic context-accurate descriptions (never positive on low scores!)
    u_cbm_str = f"{unit_cbm:.4f}"
    u_kg_str = f"{unit_kg:.2f}"

    if score >= 20:
        desc = {
            "en": f"Excellent sea-cargo density ({u_cbm_str} m³/pc, {u_kg_str} kg/pc; {pcs} pcs/ctn) — ultra-low LCL/FCL freight cost per unit to Colombo port.",
            "si": f"ඉතා විශිෂ්ට මුහුදු ප්‍රවාහන කාර්යක්ෂමතාවයක් ({u_cbm_str} m³/pc, {u_kg_str} kg/pc; පෙට්ටියකට කෑලි {pcs}) — කොළඹ වරායට ඉතා අඩු ප්‍රවාහන පිරිවැයක්.",
            "zh": f"极佳的海运集装箱装载密度（单件 {u_cbm_str} m³，{u_kg_str} kg；{pcs}件/箱），发往科伦坡港口的单件海运费极低。",
            "es": f"Excelente eficiencia de carga marítima ({u_cbm_str} m³/ud, {u_kg_str} kg/ud; {pcs} uds/caja) — costo de flete mínimo hacia Colombo."
        }
    elif score >= 14:
        desc = {
            "en": f"Good slim-profile sea cargo efficiency ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — flat carton packs well in LCL/FCL containers.",
            "si": f"හොඳ මුහුදු ප්‍රවාහන යෝග්‍යතාවයක් ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — සිහින් පෙට්ටි නිසා කන්ටේනර් තුළ පහසුවෙන් ඇසිරිය හැක.",
            "zh": f"良好的扁平化海运装载效率（单件 {u_cbm_str} m³，{u_kg_str} kg），扁平纸箱适合拼箱或整柜海运。",
            "es": f"Buena eficiencia marítima de perfil delgado ({u_cbm_str} m³/ud, {u_kg_str} kg/ud) — empaque plano ideal para contenedor."
        }
    elif score >= 9:
        desc = {
            "en": f"Moderate sea freight footprint ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — requires standard full-length mirror CBM allocation.",
            "si": f"මධ්‍යස්ථ මුහුදු ප්‍රවාහන ඉඩක් ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — සම්පූර්ණ දිග කණ්ණාඩි සඳහා සාමාන්‍ය CBM පිරිවැයක් වැයවේ.",
            "zh": f"中等海运体积与重量（单件 {u_cbm_str} m³，{u_kg_str} kg），需预留标准全身镜海运CBM成本。",
            "es": f"Volumen de flete marítimo moderado ({u_cbm_str} m³/ud, {u_kg_str} kg/ud) — requiere asignación estándar de CBM."
        }
    else:
        desc = {
            "en": f"Heavy/bulky sea freight profile ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — high CBM volume and weight increase landed freight cost in Sri Lanka.",
            "si": f"වැඩි ඉඩක් සහ බරක් ගන්නා භාණ්ඩයකි ({u_cbm_str} m³/pc, {u_kg_str} kg/pc) — ඉහළ CBM අගය නිසා ශ්‍රී ලංකාවට ගෙන්වීමේ ප්‍රවාහන ගාස්තුව වැඩිය.",
            "zh": f"大体积重货海运属性（单件 {u_cbm_str} m³，{u_kg_str} kg），较高的CBM与重量会显著增加斯里兰卡到岸运费。",
            "es": f"Perfil de carga voluminoso y pesado ({u_cbm_str} m³/ud, {u_kg_str} kg/ud) — alto CBM incrementa el costo de importación."
        }

    return {"score": score, "max": 25, "desc": desc}


def compute_margin_pillar(p):
    """
    2. Profit Margin & SL Retail Sweet Spot (0-25 pts)
    Evaluates factory RMB cost against Sri Lanka's COD impulse-buy sweet spot
    (LKR 3,500 - 8,900 retail, 15 - 45 RMB factory cost yielding 2.5x-4x markup),
    plus fast-moving multi-pack wall mirrors (3.5 - 12 RMB).
    """
    price = float(p.get("price") or 0.0)
    price2 = p.get("price2Pack")
    eff_price = float(price2) if (price2 is not None and float(price2) > 0) else price
    lkr_cost = round(price * DEFAULT_LKR_RATE)

    if 15.0 <= eff_price <= 36.0:
        score = 25
    elif 3.0 <= eff_price < 15.0:
        score = 24
    elif 36.0 < eff_price <= 45.0:
        score = 23
    elif 45.0 < eff_price <= 58.0:
        score = 20
    elif 58.0 < eff_price <= 70.0:
        score = 18
    elif 70.0 < eff_price <= 88.0:
        score = 15
    elif 88.0 < eff_price <= 105.0:
        score = 13
    elif 105.0 < eff_price <= 125.0:
        score = 10
    elif 125.0 < eff_price <= 150.0:
        score = 8
    else:
        score = 5

    score = max(0, min(25, int(score)))

    if score >= 21:
        est_retail_min = max(1290, int(round(lkr_cost * 2.8, -2)))
        est_retail_max = max(2490, int(round(lkr_cost * 3.8, -2)))
        desc = {
            "en": f"Prime SL COD margin sweet spot (Factory ¥{price:g} ≈ LKR {lkr_cost:,}) — easily supports 3x–4x retail markup (LKR {est_retail_min:,}–{est_retail_max:,}).",
            "si": f"ශ්‍රී ලංකාවේ COD වෙළඳපොළට ඉතාමත් ගැලපෙන මිල (කර්මාන්තශාලා මිල ¥{price:g} ≈ රු. {lkr_cost:,}) — 3x–4x ලාභ පරතරයක් සහිතව අලෙවි කළ හැක.",
            "zh": f"处于斯里兰卡COD黄金利润区间（出厂价 ¥{price:g} ≈ LKR {lkr_cost:,}），支持 3x–4x 零售加价空间。",
            "es": f"Punto dulce de margen COD en SL (Fábrica ¥{price:g} ≈ LKR {lkr_cost:,}) — permite margen minorista de 3x–4x."
        }
    elif score >= 15:
        desc = {
            "en": f"Healthy mid-tier furniture margin (Factory ¥{price:g} ≈ LKR {lkr_cost:,}) — strong 2.4x–3x markup for Sri Lankan online home-decor stores.",
            "si": f"හොඳ මධ්‍යම පන්තියේ ලාභ පරතරයක් (කර්මාන්තශාලා මිල ¥{price:g} ≈ රු. {lkr_cost:,}) — ගෘහ අලංකරණ වෙළඳසැල් සඳහා 2.4x–3x ලාභයක් ලබාගත හැක.",
            "zh": f"良好的中端家居利润空间（出厂价 ¥{price:g} ≈ LKR {lkr_cost:,}），适合斯里兰卡家居电商 2.4x–3x 加价销售。",
            "es": f"Margen saludable de gama media (Fábrica ¥{price:g} ≈ LKR {lkr_cost:,}) — retorno de 2.4x–3x en tiendas de decoración."
        }
    elif score >= 10:
        desc = {
            "en": f"Premium designer price tier (Factory ¥{price:g} ≈ LKR {lkr_cost:,}) — higher unit cost narrows impulse COD conversions; best for showroom/pre-order.",
            "si": f"රූපලාවන්‍ය සහ ප්‍රභූ මට්ටමේ මිලක් (කර්මාන්තශාලා මිල ¥{price:g} ≈ රු. {lkr_cost:,}) — වැඩි මිල නිසා ප්‍රදර්ශනාගාර සහ පෙර-ඇණවුම් සඳහා වඩාත් සුදුසුය.",
            "zh": f"中高端设计师款价位（出厂价 ¥{price:g} ≈ LKR {lkr_cost:,}），单价较高，更适合展厅零售或定金预售。",
            "es": f"Nivel de precio de diseño premium (Fábrica ¥{price:g} ≈ LKR {lkr_cost:,}) — menor conversión por impulso; ideal para showroom."
        }
    else:
        desc = {
            "en": f"High factory cost (¥{price:g} ≈ LKR {lkr_cost:,}) exceeds Sri Lanka's mass COD impulse threshold — requires B2B/boutique buyers.",
            "si": f"ඉහළ කර්මාන්තශාලා පිරිවැයක් (¥{price:g} ≈ රු. {lkr_cost:,}) — සාමාන්‍ය COD පාරිභෝගිකයන්ට මිල අධික බැවින් B2B හෝ සුඛෝපභෝගී ප්‍රදර්ශනාගාර සඳහා පමණක් ගැලපේ.",
            "zh": f"出厂成本较高（¥{price:g} ≈ LKR {lkr_cost:,}），超出斯里兰卡大众COD冲动消费区间，仅适合B2B或高端精品店。",
            "es": f"Costo de fábrica elevado (¥{price:g} ≈ LKR {lkr_cost:,}) fuera del rango masivo COD en SL — requiere clientes B2B/boutique."
        }

    return {"score": score, "max": 25, "desc": desc}


def compute_demand_pillar(p):
    """
    3. Local Consumer Demand & Viral Appeal (0-25 pts)
    Evaluates Sri Lankan household utility, dressing/grooming necessity,
    TikTok/Instagram viral home aesthetics, and climate/market fit.
    """
    zh = str(p.get("zh") or "")
    en = str(p.get("en") or "").lower()
    cat = str(p.get("category") or "")
    size = str(p.get("size") or "")
    price = float(p.get("price") or 0.0)

    # Check climate-mismatched items if any ever appear
    if any(k in en for k in ("snow", "heater", "winter", "ski")):
        score = 3
    elif cat == "hanging-mirrors":
        # Compact wall/bathroom/dressing mirrors have massive everyday demand across SL homes, hostels, salons
        if price <= 5.5:
            score = 24
        elif price <= 8.5:
            score = 22
        else:
            score = 21
    elif cat == "metal-mirrors":
        # Lightweight arch/rounded full-length & rolling mirrors are top sellers on SL Facebook/Daraz/TikTok
        if "轮镜" in zh or "rolling" in en:
            score = 22
        elif price <= 35.0:
            score = 23
        elif price <= 50.0:
            score = 20
        else:
            score = 17
    elif cat == "led-mirrors":
        # High viral TikTok/salon/bridal makeup appeal
        score = 20
    elif cat == "rotating-mirrors":
        # 2-in-1 rotating bookshelf/pegboard mirrors have strong viral appeal for compact urban rooms
        if price <= 105.0:
            score = 19
        elif price <= 135.0:
            score = 16
        else:
            score = 13
    elif cat == "velvet-mirrors":
        # Viral wavy/cloud/teddy velvet mirrors for bedrooms & boutiques
        if "160*50" in size or "160×50" in size:
            score = 18
        elif "160*60" in size or "160×60" in size:
            score = 16
        else:
            score = 12
    else:
        # Vintage wood-board stand mirrors
        if ("150*40" in size or "155*40" in size or "160*50" in size or "150×40" in size or "155×40" in size or "160×50" in size) and price <= 80.0:
            score = 19
        elif price <= 95.0:
            score = 16
        elif price <= 110.0:
            score = 14
        else:
            score = 11

    score = max(0, min(25, int(score)))

    if score >= 20:
        desc = {
            "en": "High everyday household & TikTok/Facebook viral demand across Sri Lankan bedrooms, salons, boarding rooms, and boutiques.",
            "si": "ශ්‍රී ලංකාවේ නිවාස, රූපලාවන්‍යාගාර (Salons), නේවාසිකාගාර සහ TikTok/Facebook හරහා ඉතා ඉහළ දෛනික ඉල්ලුමක් පවතී.",
            "zh": "在斯里兰卡家庭卧室、美发美容沙龙、学生公寓及TikTok/Facebook社交电商上拥有极高的日常刚需与爆款热度。",
            "es": "Alta demanda diaria y atractivo viral en TikTok/Facebook para hogares, salones de belleza y boutiques en Sri Lanka."
        }
    elif score >= 15:
        desc = {
            "en": "Strong aesthetic & lifestyle appeal among urban Sri Lankan home-decor shoppers, bridal studios, and fashion pages.",
            "si": "නාගරික ගෘහ අලංකරණ පාරිභෝගිකයන්, මනාලියන් හැඩගැන්වීමේ ආයතන සහ විලාසිතා ප්‍රදර්ශනාගාර අතර ඉහළ ආකර්ෂණයක් ඇත.",
            "zh": "在斯里兰卡城市家居装饰买家、婚纱摄影工作室及服装店中具有较强的网红审美吸引力。",
            "es": "Fuerte atractivo estético entre compradores urbanos de decoración, estudios nupciales y tiendas de moda."
        }
    else:
        desc = {
            "en": "Niche oversized/specialty format — limited to luxury villas, commercial clothing showrooms, or interior designers.",
            "si": "විශේෂිත විශාල ප්‍රමාණයේ මාදිලියකි — සුඛෝපභෝගී නිවාස, ඇඳුම් ප්‍රදර්ශනාගාර හෝ ගෘහ නිර්මාණ ශිල්පීන්ට පමණක් සීමා වූ ඉල්ලුමකි.",
            "zh": "大尺寸或小众特殊款式，受众主要局限于高端别墅、商业服装展厅或室内设计师采购。",
            "es": "Formato grande de nicho — demanda limitada a villas de lujo, showrooms comerciales o diseñadores de interiores."
        }

    return {"score": score, "max": 25, "desc": desc}


def compute_risk_pillar(p):
    """
    4. Operational & COD Return Risk (0-25 pts)
    Evaluates durability, ease of use, transit/glass safety, packaging protection,
    and high-ticket COD rejection risk.
    """
    pcs = max(1, int(p.get("pcsPerCarton") or 1))
    kg_val = p.get("kg")
    kg = float(kg_val) if (kg_val is not None and kg_val > 0) else 10.0
    unit_kg = kg / pcs
    price = float(p.get("price") or 0.0)
    cat = str(p.get("category") or "")
    mat = str(p.get("material") or "")

    if cat == "hanging-mirrors":
        if unit_kg <= 0.45 and price <= 4.5:
            score = 22
        elif unit_kg <= 0.85 and price <= 6.5:
            score = 20
        elif unit_kg <= 1.25:
            score = 18
        else:
            score = 16
    elif cat == "metal-mirrors":
        if unit_kg <= 3.5 and price <= 25.0:
            score = 21
        elif unit_kg <= 5.0 and price <= 40.0:
            score = 19
        elif unit_kg <= 7.5 and price <= 55.0:
            score = 16
        else:
            score = 13
    elif cat == "led-mirrors":
        # LED driver + glass requires careful courier handling
        score = 12
    elif unit_kg <= 11.5 and price <= 70.0:
        score = 15
    elif unit_kg <= 14.5 and price <= 98.0:
        score = 13
    elif unit_kg <= 17.5 and price <= 125.0:
        score = 10
    elif unit_kg <= 20.0 and price <= 150.0:
        score = 8
    else:
        score = 6

    score = max(0, min(25, int(score)))

    if score >= 18:
        desc = {
            "en": f"Low COD return & transit risk ({unit_kg:.2f} kg/pc) — compact/framed construction handles local courier delivery smoothly.",
            "si": f"අඩු ප්‍රවාහන සහ COD ප්‍රතික්ෂේප වීමේ අවදානම ({unit_kg:.2f} kg/pc) — සැහැල්ලු සහ ආරක්ෂිත නිමාව නිසා කුරියර් මගින් පහසුවෙන් බෙදාහැරිය හැක.",
            "zh": f"低COD拒收与运输风险（单件 {unit_kg:.2f} kg），轻便加固结构适合斯里兰卡本地快递派送。",
            "es": f"Bajo riesgo de devolución COD y transporte ({unit_kg:.2f} kg/ud) — estructura ligera segura para mensajería local."
        }
    elif score >= 13:
        desc = {
            "en": f"Moderate courier handling risk ({unit_kg:.2f} kg/pc, 5-layer kraft carton) — advise corner-foam reinforcement for outstation COD.",
            "si": f"මධ්‍යස්ථ ප්‍රවාහන අවදානමක් ({unit_kg:.2f} kg/pc, තට්ටු 5 කාඩ්බෝඩ් පෙට්ටිය) — දුර බැහැර කුරියර් ප්‍රවාහනයේදී අමතර ආරක්ෂිත ඇසුරුම් නිර්දේශ කෙරේ.",
            "zh": f"中等物流派送风险（单件 {unit_kg:.2f} kg，5层牛皮纸箱），发往外省COD建议增加护角泡沫保护。",
            "es": f"Riesgo logístico moderado ({unit_kg:.2f} kg/ud, caja kraft de 5 capas) — se recomienda refuerzo de esquinas."
        }
    else:
        desc = {
            "en": f"Elevated fragile-cargo & high-ticket COD return risk ({unit_kg:.2f} kg/pc) — collect partial advance deposit before dispatching.",
            "si": f"බිඳෙනසුලු සහ වැඩි බරැති ({unit_kg:.2f} kg/pc) භාණ්ඩයක් බැවින් COD ප්‍රතික්ෂේප වීමේ අවදානම වැඩිය — යැවීමට පෙර අත්තිකාරම් මුදලක් (Advance) ලබාගන්න.",
            "zh": f"较高的大件易碎品运输及高客单COD拒收风险（单件 {unit_kg:.2f} kg），建议收取部分定金后再安排专车或物流派送。",
            "es": f"Riesgo elevado de carga frágil y rechazo COD de alto valor ({unit_kg:.2f} kg/ud) — solicite anticipo antes del envío."
        }

    return {"score": score, "max": 25, "desc": desc}


def evaluate_product(p):
    """
    Computes SL-WPI 100-point score, tier, rate, breakdown, and localized overall reason.
    Guarantees freight + margin + demand + risk == winScore.
    """
    freight = compute_freight_pillar(p)
    margin = compute_margin_pillar(p)
    demand = compute_demand_pillar(p)
    risk = compute_risk_pillar(p)

    win_score = int(freight["score"] + margin["score"] + demand["score"] + risk["score"])
    assert 0 <= win_score <= 100

    if win_score >= 85:
        tier = "mega"
    elif win_score >= 70:
        tier = "strong"
    elif win_score >= 50:
        tier = "niche"
    else:
        tier = "low"

    pcs = max(1, int(p.get("pcsPerCarton") or 1))
    price = float(p.get("price") or 0.0)
    lkr_cost = round(price * DEFAULT_LKR_RATE)

    if tier == "mega":
        reason = {
            "en": f"Top-tier Sri Lanka Sea Cargo Mega Winner ({win_score}/100): ultra-efficient freight, prime ¥{price:g} (≈LKR {lkr_cost:,}) COD margin sweet spot, and massive everyday household demand.",
            "si": f"ශ්‍රී ලංකාවේ මුහුදු ප්‍රවාහන සුපිරි ජයග්‍රාහී භාණ්ඩයකි ({win_score}/100): ඉතා අඩු ප්‍රවාහන පිරිවැය, ඉහළ ලාභ පරතරය (¥{price:g} ≈ රු. {lkr_cost:,}) සහ ඉහළම පාරිභෝගික ඉල්ලුම.",
            "zh": f"斯里兰卡海运超级爆款（{win_score}/100）：极低海运成本、黄金COD利润空间（¥{price:g} ≈ LKR {lkr_cost:,}）及超高家庭刚需。",
            "es": f"Mega Ganador para Sri Lanka por carga marítima ({win_score}/100): flete ultraeficiente, excelente margen COD y altísima demanda."
        }
    elif tier == "strong":
        reason = {
            "en": f"Strong Sea Cargo Winner ({win_score}/100): balanced flat-pack container efficiency, attractive ¥{price:g} (≈LKR {lkr_cost:,}) wholesale cost, and high local home-decor demand.",
            "si": f"ඉහළ විකුණුම් හැකියාවක් ඇති ජයග්‍රාහී භාණ්ඩයකි ({win_score}/100): හොඳ මුහුදු ප්‍රවාහන කාර්යක්ෂමතාව, ආකර්ෂණීය තොග මිල (¥{price:g} ≈ රු. {lkr_cost:,}) සහ ඉහළ වෙළඳපොළ ඉල්ලුම.",
            "zh": f"斯里兰卡海运强力爆款（{win_score}/100）：良好的海运装载率、极具竞争力的批发价（¥{price:g} ≈ LKR {lkr_cost:,}）与强劲市场需求。",
            "es": f"Ganador Fuerte de carga marítima ({win_score}/100): buen flete en contenedor, costo atractivo (¥{price:g}) y alta demanda local."
        }
    elif tier == "niche":
        reason = {
            "en": f"Niche Designer Catalog Item ({win_score}/100): strong visual appeal for bedrooms & boutiques, but moderate-to-high CBM and ¥{price:g} cost work best for showroom or pre-order sales.",
            "si": f"විශේෂිත වෙළඳපොළ භාණ්ඩයකි ({win_score}/100): අලංකාර නිමාවක් ඇති නමුත් මධ්‍යස්ථ ප්‍රවාහන ඉඩ සහ මිල (¥{price:g} ≈ රු. {lkr_cost:,}) නිසා ප්‍රදර්ශනාගාර සහ පෙර-ඇණවුම් සඳහා වඩාත් සුදුසුය.",
            "zh": f"细分市场设计师款（{win_score}/100）：外观颜值高，但因海运体积与单价（¥{price:g} ≈ LKR {lkr_cost:,}）适中偏高，更适合展厅或预售模式。",
            "es": f"Producto de Nicho ({win_score}/100): gran atractivo visual, pero su volumen CBM y costo (¥{price:g}) son mejores para showroom o preventa."
        }
    else:
        reason = {
            "en": f"Low Mass-COD Feasibility ({win_score}/100): large/heavy carton footprint and high factory cost (¥{price:g} ≈ LKR {lkr_cost:,}) create high freight and COD return risk; import only on confirmed B2B orders.",
            "si": f"අඩු COD යෝග්‍යතාවයක් ({win_score}/100): විශාල බර/ප්‍රමාණය සහ ඉහළ මිල (¥{price:g} ≈ රු. {lkr_cost:,}) නිසා ප්‍රවාහන හා COD අවදානම වැඩිය; ස්ථිර B2B ඇණවුම් සඳහා පමණක් ආනයනය කරන්න.",
            "zh": f"大众COD可行性较低（{win_score}/100）：体积大、重量重且单价高（¥{price:g} ≈ LKR {lkr_cost:,}），海运费与拒收风险高，建议仅按B2B确定订单进口。",
            "es": f"Baja viabilidad para COD masivo ({win_score}/100): gran volumen/peso y alto costo (¥{price:g}) elevan el riesgo logístico; importar solo bajo pedido B2B."
        }

    p["winScore"] = win_score
    p["winRate"] = f"{win_score}%"
    p["winTier"] = tier
    p["winTierLabel"] = TIER_META[tier]
    p["winReason"] = reason
    p["winBreakdown"] = {
        "freight": freight,
        "margin": margin,
        "demand": demand,
        "risk": risk
    }
    return p


def score_all_products(products):
    for p in products:
        evaluate_product(p)
    return products


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    products_js = os.path.join(base_dir, "data", "products.js")
    if not os.path.exists(products_js):
        print(f"products.js not found at {products_js}. Run build.py first.")
        return

    with open(products_js, "r", encoding="utf-8") as f:
        content = f.read()

    m = re.search(r"window\.CATALOG\s*=\s*(\{.*\})\s*;\s*$", content, re.DOTALL)
    if not m:
        raise ValueError("Could not parse window.CATALOG in products.js")

    catalog = json.loads(m.group(1))
    products = catalog.get("products", [])
    score_all_products(products)

    tiers = {"mega": 0, "strong": 0, "niche": 0, "low": 0}
    for p in products:
        tiers[p["winTier"]] += 1

    out_js = "window.CATALOG = " + json.dumps(catalog, ensure_ascii=False, indent=2) + ";\n"
    with open(products_js, "w", encoding="utf-8") as f:
        f.write(out_js)

    print(f"Scored {len(products)} products successfully: {tiers}")


if __name__ == "__main__":
    main()
