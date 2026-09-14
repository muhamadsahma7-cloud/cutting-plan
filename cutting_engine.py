"""Core cutting-plan calculation engine.

Ported from the JS implementation in web/script.js so the optimization
and MTO math stay identical between the web app and this Streamlit app.
"""

from __future__ import annotations

from typing import Any


def generate_piece_id(materials: list[dict]) -> str:
    """Return the next unused piece id (A1, A2, ... A10, B1, ...)."""
    used_ids = {p["id"] for m in materials for p in m.get("pieces", [])}
    n = len(used_ids) + 1
    while True:
        prefix = chr(65 + (n - 1) // 10)
        number = (n - 1) % 10 + 1
        pid = f"{prefix}{number}"
        if pid not in used_ids:
            return pid
        n += 1


def optimize_cutting_plan(material: dict, kerf: float) -> list[dict]:
    """First-fit-decreasing bin packing over the material's stock pool.

    Returns a list of bars: {"barLength": float, "pieces": [piece, ...]}
    where each piece has id / length / originalId / description.
    """
    pieces = material.get("pieces", [])
    if not pieces:
        return []

    all_pieces = []
    for piece in pieces:
        for i in range(int(piece["quantity"])):
            all_pieces.append({
                "id": f"{piece['id']}-{i + 1}",
                "length": piece["length"],
                "originalId": piece["id"],
                "description": piece.get("description", ""),
            })

    all_pieces.sort(key=lambda p: p["length"], reverse=True)

    stocks = [{"length": material["standardLength"], "qty": material.get("qtyStock", 0) or 0}]
    stocks += [{"length": s["length"], "qty": s.get("qty", 0) or 0} for s in material.get("additionalStocks", [])]
    has_defined_stock = any(s["qty"] > 0 for s in stocks)

    available_pool = None
    if has_defined_stock:
        available_pool = []
        for s in stocks:
            available_pool.extend([s["length"]] * s["qty"])
        available_pool.sort(reverse=True)

    bars: list[dict] = []

    for piece in all_pieces:
        placed = False
        piece_need = piece["length"] + kerf

        for bar in bars:
            used = sum(p["length"] + kerf for p in bar["pieces"])
            if used + piece_need <= bar["barLength"]:
                bar["pieces"].append(piece)
                placed = True
                break

        if not placed:
            if available_pool is None:
                bar_len = material["standardLength"]
            else:
                best_idx, best_len = -1, float("inf")
                for i, length in enumerate(available_pool):
                    if length >= piece_need and length < best_len:
                        best_idx, best_len = i, length
                if best_idx >= 0:
                    bar_len = available_pool.pop(best_idx)
                else:
                    # No stock fits — open an overflow bar at standard length.
                    bar_len = material["standardLength"]
            bars.append({"barLength": bar_len, "pieces": [piece]})

    return bars


def calc_required_bars(material: dict, kerf: float) -> int:
    return len(optimize_cutting_plan(material, kerf))


def material_metrics(material: dict, kerf: float) -> dict[str, Any]:
    """Per-material summary numbers used across the dashboard/MTO views."""
    pieces = material.get("pieces", [])
    total_length = sum(p["length"] * p["quantity"] for p in pieces)
    total_weight = total_length / 1000 * material.get("weightPerMeter", 0)

    cutting_plan = optimize_cutting_plan(material, kerf)
    required_bars = len(cutting_plan)
    bought_length = sum(b["barLength"] for b in cutting_plan)
    kerf_loss = sum(len(b["pieces"]) * kerf for b in cutting_plan)
    used_length = sum(p["length"] for b in cutting_plan for p in b["pieces"])
    waste = sum(
        max(0.0, b["barLength"] - sum(p["length"] + kerf for p in b["pieces"]))
        for b in cutting_plan
    )

    qty_stock = material.get("qtyStock", 0) or 0
    add_stocks = material.get("additionalStocks", []) or []
    total_stock_qty = qty_stock + sum(s.get("qty", 0) or 0 for s in add_stocks)
    balance = total_stock_qty - required_bars

    efficiency = (used_length / bought_length * 100) if bought_length > 0 else 0.0
    surplus_pct = ((bought_length - total_length) / bought_length * 100) if bought_length > 0 else 0.0

    return {
        "totalLength": total_length,
        "totalWeight": total_weight,
        "requiredBars": required_bars,
        "boughtLength": bought_length,
        "kerfLoss": kerf_loss,
        "waste": waste,
        "totalStockQty": total_stock_qty,
        "balance": balance,
        "efficiency": efficiency,
        "surplusPct": surplus_pct,
        "cuttingPlan": cutting_plan,
    }


def project_totals(materials: list[dict], kerf: float) -> dict[str, Any]:
    total_pieces = 0
    total_length = 0.0
    total_weight = 0.0
    total_bought = 0.0

    for material in materials:
        m = material_metrics(material, kerf)
        total_pieces += sum(p["quantity"] for p in material.get("pieces", []))
        total_length += m["totalLength"]
        total_weight += m["totalWeight"]
        total_bought += m["boughtLength"]

    overall_surplus = ((total_bought - total_length) / total_bought * 100) if total_bought > 0 else 0.0

    return {
        "totalPieces": total_pieces,
        "totalLength": total_length,
        "totalWeight": total_weight,
        "totalBought": total_bought,
        "overallSurplus": overall_surplus,
    }
