"""Cutting Plan & MTO — Streamlit edition.

Reuses the same Supabase backend (auth + projects table) as the existing
web app at cuttingnestpro.netlify.app, so accounts and saved projects are
shared between the two.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

import cutting_engine as engine
import supa
import theme

st.set_page_config(page_title="Cutting Plan & MTO", page_icon="📐", layout="wide")
theme.inject()

COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
GRADE_OPTIONS = ["S235", "S275", "S355", "S355JR", "S355J2", "A36", "A572 Gr50", "A992"]

TAB_OVERVIEW = "🏠 Overview"
TAB_MATERIALS = "🧱 Materials & Pieces"
TAB_VISUALIZATION = "📊 Cutting Plan"
TAB_MTO = "📋 MTO Summary"
TAB_EXPORT = "📤 Export"
TAB_ADMIN = "🛡️ Admin"


# ── Session state defaults ──────────────────────────────────────────────────

def _init_state():
    defaults = {
        "materials": [],
        "selected_material_id": None,
        "current_project_id": None,
        "current_project_name": "Untitled Project",
        "project_date": "",
        "project_engineer": "",
        "kerf": 2.0,
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)


_init_state()


def _material_by_id(mid):
    return next((m for m in st.session_state.materials if m["id"] == mid), None)


@st.cache_data(show_spinner=False)
def cached_material_metrics(material: dict, kerf: float) -> dict:
    """Cached wrapper around the bin-packing optimizer.

    Keyed on the material's own content + kerf, so unrelated reruns (typing
    in the sidebar, editing a different material) hit the cache instead of
    re-running first-fit-decreasing packing from scratch.
    """
    return engine.material_metrics(material, kerf)


# ── Auth screen ──────────────────────────────────────────────────────────────

def render_login():
    theme.banner("Cutting Plan & MTO", "Linear cutting optimization & material take-off")

    tab_in, tab_up = st.tabs(["Sign In", "Create Account"])

    with tab_in:
        with st.form("signin_form"):
            email = st.text_input("Email", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
        if submitted:
            ok, msg = supa.sign_in(email, password)
            if ok:
                st.rerun()
            else:
                st.error(msg or "Sign in failed.")

        with st.expander("Forgot password?"):
            reset_email = st.text_input("Email", key="reset_email")
            if st.button("Send reset link", key="reset_btn"):
                if not reset_email.strip():
                    st.warning("Enter your email address first.")
                else:
                    ok, msg = supa.reset_password(reset_email.strip())
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.caption("The reset link opens cuttingnestpro.netlify.app to finish setting your new password — then come back here to sign in.")

    with tab_up:
        with st.form("signup_form"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password (min 8 chars)", type="password", key="signup_password")
            submitted = st.form_submit_button("Create Account", use_container_width=True)
        if submitted:
            ok, msg = supa.sign_up(email, password)
            if ok:
                st.success(msg)
            else:
                st.error(msg or "Sign up failed.")


# ── Project loading/saving ──────────────────────────────────────────────────

def _apply_project_data(data: dict):
    info = data.get("projectInfo", {})
    st.session_state.current_project_name = info.get("name", "Untitled Project")
    st.session_state.project_date = info.get("date", "")
    st.session_state.project_engineer = info.get("engineer", "")
    st.session_state.materials = data.get("materials", [])
    st.session_state.selected_material_id = data.get("selectedMaterialId")
    st.session_state.kerf = (data.get("settings") or {}).get("kerf", 2.0)


def _build_project_snapshot() -> dict:
    return {
        "projectInfo": {
            "name": st.session_state.current_project_name,
            "date": st.session_state.project_date,
            "engineer": st.session_state.project_engineer,
        },
        "materials": st.session_state.materials,
        "selectedMaterialId": st.session_state.selected_material_id,
        "settings": {"kerf": st.session_state.kerf},
        "version": "streamlit-1.0",
    }


def render_sidebar(user):
    with st.sidebar:
        st.markdown(f"### 👤 {user.email}")

        status = supa.cached_get_access_status(user.id, user.created_at)
        if status["active"]:
            label = "Trial" if status["isTrial"] else status["plan"].title()
            st.success(f"**{label}** · {status['daysLeft']} day(s) left")
        else:
            st.error("Access expired — contact admin to renew.")

        if st.button("🚪 Log out", use_container_width=True):
            supa.sign_out()
            st.rerun()

        st.divider()
        st.markdown("#### 📁 Project")

        try:
            projects = supa.cached_list_projects(user.id)
        except Exception as exc:  # noqa: BLE001
            projects = []
            st.warning(f"Could not load project list: {exc}")

        names = [p["name"] for p in projects]
        ids = [p["id"] for p in projects]
        current_idx = ids.index(st.session_state.current_project_id) if st.session_state.current_project_id in ids else None

        choice = st.selectbox(
            "Open a saved project",
            options=range(len(names)),
            format_func=lambda i: names[i],
            index=current_idx,
            placeholder="Select a project…",
        )
        if choice is not None and ids[choice] != st.session_state.current_project_id:
            data = supa.load_project(ids[choice])
            if data:
                st.session_state.current_project_id = data["id"]
                _apply_project_data(data["data"])
                st.rerun()

        with st.expander("+ New project"):
            new_name = st.text_input("Project name", value="New Cutting Plan Project", key="new_project_name")
            if st.button("Create", key="create_project_btn"):
                initial = {
                    "projectInfo": {"name": new_name, "date": "", "engineer": ""},
                    "materials": [], "selectedMaterialId": None,
                    "settings": {"kerf": 2.0}, "version": "streamlit-1.0",
                }
                new_id = supa.create_project(user.id, new_name, initial)
                supa.cached_list_projects.clear()
                st.session_state.current_project_id = new_id
                _apply_project_data(initial)
                st.rerun()

        st.divider()
        st.session_state.current_project_name = st.text_input("Project name", value=st.session_state.current_project_name)
        st.session_state.project_date = st.text_input("Date", value=st.session_state.project_date)
        st.session_state.project_engineer = st.text_input("Engineer", value=st.session_state.project_engineer)
        st.session_state.kerf = st.number_input("Kerf (mm)", min_value=0.0, value=float(st.session_state.kerf), step=0.5)

        if st.session_state.current_project_id:
            if st.button("💾 Save to cloud", type="primary", use_container_width=True):
                supa.save_project(
                    st.session_state.current_project_id,
                    st.session_state.current_project_name,
                    _build_project_snapshot(),
                )
                supa.cached_list_projects.clear()
                st.toast("Saved!", icon="✅")
        else:
            st.info("Create or open a project above to enable saving.")


# ── Materials & pieces tab ──────────────────────────────────────────────────

def render_materials_tab():
    st.markdown("#### 🧱 Materials")

    mats = st.session_state.materials
    base_rows = [{
        "id": m["id"], "Material Name": m["name"], "Type": m["type"],
        "Material Grade": m.get("materialGrade", ""),
        "Standard Length (mm)": m["standardLength"],
        "Weight/m (kg/m)": m["weightPerMeter"], "Unit Price ($)": m.get("unitPrice", 0.0),
        "Qty Stock": m.get("qtyStock", 0),
    } for m in mats]
    df = pd.DataFrame(base_rows, columns=[
        "id", "Material Name", "Type", "Material Grade", "Standard Length (mm)",
        "Weight/m (kg/m)", "Unit Price ($)", "Qty Stock",
    ])

    with st.container(border=True):
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_order=["Material Name", "Type", "Material Grade", "Standard Length (mm)", "Weight/m (kg/m)", "Unit Price ($)", "Qty Stock"],
            column_config={
                "Type": st.column_config.SelectboxColumn(options=[
                    "Steel Beam", "Steel Plate", "Angle Bar", "Channel", "Pipe", "Flat Bar", "Round Bar", "Rebar",
                ]),
                "Material Grade": st.column_config.SelectboxColumn(options=GRADE_OPTIONS),
            },
            key="materials_editor",
        )

    def _str(v, default=""):
        return default if pd.isna(v) else str(v).strip()

    def _num(v, cast, default=0):
        return default if pd.isna(v) else cast(v)

    by_old_id = {m["id"]: m for m in mats}
    new_materials = []
    for _, row in edited.iterrows():
        # A freshly-added blank row has NaN cells, and str(NaN) == "nan"
        # (truthy!) — so this must check pd.isna directly, not just
        # falsiness, or blank rows silently become materials named "nan".
        name = _str(row["Material Name"])
        if not name:
            continue
        old = by_old_id.get(row["id"])
        material = dict(old) if old else {
            "id": int(time.time() * 1000) + len(new_materials),
            "pieces": [], "additionalStocks": [], "crossSection": "",
        }
        material.update({
            "name": name, "type": _str(row["Type"]) or "Steel Beam",
            "materialGrade": _str(row["Material Grade"]),
            "standardLength": _num(row["Standard Length (mm)"], float),
            "weightPerMeter": _num(row["Weight/m (kg/m)"], float),
            "unitPrice": _num(row["Unit Price ($)"], float),
            "qtyStock": _num(row["Qty Stock"], int),
        })
        new_materials.append(material)
    st.session_state.materials = new_materials

    if not new_materials:
        st.info("Add a material above to get started.")
        return

    names = [m["name"] for m in new_materials]
    ids = [m["id"] for m in new_materials]
    default_idx = ids.index(st.session_state.selected_material_id) if st.session_state.selected_material_id in ids else 0
    sel_idx = st.selectbox("Selected material", options=range(len(names)), format_func=lambda i: names[i], index=default_idx)
    st.session_state.selected_material_id = ids[sel_idx]
    material = new_materials[sel_idx]

    metrics = cached_material_metrics(material, st.session_state.kerf)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bars Required", metrics["requiredBars"])
    c2.metric("Stock Balance", f"{metrics['balance']:+d}" if isinstance(metrics["balance"], int) else metrics["balance"])
    c3.metric("Total Weight (kg)", f"{metrics['totalWeight']:.1f}")
    c4.metric("Efficiency", f"{metrics['efficiency']:.1f}%")

    st.markdown("#### 📦 Additional stock lengths")
    st.caption("Besides the standard length above — e.g. shorter offcut lengths already in stock.")
    with st.container(border=True):
        add_df = pd.DataFrame(material.get("additionalStocks", []) or [], columns=["length", "qty"])
        add_df = add_df.rename(columns={"length": "Length (mm)", "qty": "Qty"})
        add_edited = st.data_editor(add_df, num_rows="dynamic", use_container_width=True, hide_index=True, key="addstock_editor")
    material["additionalStocks"] = [
        {"length": float(r["Length (mm)"]), "qty": int(r["Qty"]) if pd.notna(r["Qty"]) else 0}
        for _, r in add_edited.iterrows() if pd.notna(r["Length (mm)"]) and r["Length (mm)"] > 0
    ]

    st.markdown("#### ✂️ Cutting pieces")

    with st.expander("📥 Bulk import from Excel/CSV"):
        template_buf = BytesIO()
        template_df = pd.DataFrame([
            {"Piece ID": "A1", "Length (mm)": 6500, "Quantity": 4, "Notes": "Example row"},
            {"Piece ID": "A2", "Length (mm)": 3200, "Quantity": 8, "Notes": ""},
        ])
        with pd.ExcelWriter(template_buf, engine="openpyxl") as writer:
            template_df.to_excel(writer, sheet_name="Pieces", index=False)
        st.download_button(
            "⬇️ Download blank template", data=template_buf.getvalue(),
            file_name="cutting_pieces_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pieces_template_dl",
        )

        uploaded = st.file_uploader(
            "Upload filled-in template", type=["xlsx", "xls", "csv"], key=f"pieces_upload_{material['id']}",
        )
        if uploaded is not None:
            guard_key = f"_pieces_import_done_{material['id']}"
            if st.session_state.get(guard_key) != uploaded.file_id:
                try:
                    import_df = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
                except Exception as exc:  # noqa: BLE001
                    import_df = None
                    st.error(f"Could not read file: {exc}")

                if import_df is not None:
                    def _find_col(df, *names):
                        for n in names:
                            if n in df.columns:
                                return n
                        return None

                    id_col = _find_col(import_df, "Piece ID", "ID", "id")
                    len_col = _find_col(import_df, "Length (mm)", "Length (m)", "Length", "length")
                    qty_col = _find_col(import_df, "Quantity", "Qty", "qty", "quantity")
                    notes_col = _find_col(import_df, "Notes", "notes")

                    if not id_col or not len_col or not qty_col:
                        st.error("File must have at least Piece ID, Length, and Quantity columns.")
                    else:
                        existing = {p["id"]: p for p in material.get("pieces", [])}
                        added = updated = skipped = 0
                        for _, r in import_df.iterrows():
                            pid = str(r[id_col]).strip() if pd.notna(r[id_col]) else ""
                            length, qty = r[len_col], r[qty_col]
                            if not pid or pd.isna(length) or not length or pd.isna(qty) or not qty:
                                skipped += 1
                                continue
                            notes = str(r[notes_col]).strip() if notes_col and pd.notna(r[notes_col]) else ""
                            if pid in existing:
                                updated += 1
                            else:
                                added += 1
                            # description mirrors the parent material's name (see the
                            # Cutting pieces grid below) — the template's own
                            # Description column, if present, is ignored.
                            existing[pid] = {
                                "id": pid, "description": material["name"],
                                "length": float(length), "quantity": int(qty), "notes": notes,
                            }

                        material["pieces"] = list(existing.values())
                        st.session_state[guard_key] = uploaded.file_id
                        st.session_state.pop("pieces_editor", None)  # force the grid to reload the new data
                        st.success(
                            f"Import complete: {added} added, {updated} updated"
                            + (f", {skipped} skipped (missing ID/length/quantity)" if skipped else "") + "."
                        )
                        st.rerun()

    with st.container(border=True):
        pieces_df = pd.DataFrame(material.get("pieces", []), columns=["id", "length", "quantity", "notes"])
        pieces_df = pieces_df.rename(columns={"length": "Length (mm)", "quantity": "Quantity", "notes": "Notes"})
        # Material Name / Type / Material Grade are reference columns mirroring
        # the parent material — read-only, not stored per piece.
        pieces_df.insert(1, "Material Name", material["name"])
        pieces_df.insert(2, "Type", material["type"])
        pieces_df.insert(3, "Material Grade", material.get("materialGrade", ""))
        pieces_edited = st.data_editor(
            pieces_df, num_rows="dynamic", use_container_width=True, hide_index=True,
            column_order=["id", "Material Name", "Type", "Material Grade", "Length (mm)", "Quantity", "Notes"],
            column_config={
                "id": st.column_config.TextColumn("ID", help="Leave blank on new rows to auto-generate"),
                "Material Name": st.column_config.TextColumn(disabled=True, help="From the selected material, above"),
                "Type": st.column_config.TextColumn(disabled=True, help="From the selected material, above"),
                "Material Grade": st.column_config.TextColumn(disabled=True, help="From the selected material, above"),
            },
            key="pieces_editor",
        )

    new_pieces = []
    for _, row in pieces_edited.iterrows():
        length, qty = row["Length (mm)"], row["Quantity"]
        # pd.isna() must come before any truthiness check — NaN is truthy
        # in Python, so `not row["Quantity"]` alone lets a blank Quantity
        # cell through, and int(NaN) then raises ValueError.
        if pd.isna(length) or not length or pd.isna(qty) or not qty:
            continue
        pid = str(row["id"]).strip() if pd.notna(row["id"]) and str(row["id"]).strip() else None
        if pid is None:
            pid = engine.generate_piece_id(st.session_state.materials)
        notes = str(row["Notes"]).strip() if pd.notna(row["Notes"]) else ""
        new_pieces.append({
            "id": pid, "description": material["name"],
            "length": float(length), "quantity": int(qty),
            "notes": notes,
        })
    material["pieces"] = new_pieces

    if material["pieces"]:
        piece_rows = [{
            "Piece ID": p["id"], "Material Name": material["name"], "Type": material["type"],
            "Material Grade": material.get("materialGrade", ""), "Length (mm)": p["length"],
            "Quantity": p["quantity"], "Total Length (mm)": p["length"] * p["quantity"],
            "Weight (kg)": round(p["length"] * p["quantity"] / 1000 * material["weightPerMeter"], 1),
            "Notes": p.get("notes", ""),
        } for p in material["pieces"]]
        pieces_buf = BytesIO()
        with pd.ExcelWriter(pieces_buf, engine="openpyxl") as writer:
            pd.DataFrame(piece_rows).to_excel(writer, sheet_name="Pieces", index=False)
        st.download_button(
            f"⬇️ Export {material['name']} pieces to Excel", data=pieces_buf.getvalue(),
            file_name=f"{material['name'].replace(' ', '_')}_pieces.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"pieces_export_{material['id']}",
        )


# ── Visualization tab ────────────────────────────────────────────────────────

# Standard printable page (A3 landscape, inches) — used only for the PDF
# export, so materials with many bars paginate onto multiple properly-sized
# sheets instead of one oversized page that prints squished/illegible.
PDF_PAGE_W, PDF_PAGE_H = 16.54, 11.69
PDF_HEADER_H, PDF_FOOTER_H, PDF_BAR_ROW_H = 1.3, 0.5, 0.68


def _draw_cutting_bars(ax, bars: list[dict], start_index: int = 0):
    """Draw one page's worth of bars. start_index offsets the displayed
    'Bar N' label so pagination doesn't restart the count at 1."""
    n = len(bars)
    for i, bar in enumerate(bars):
        y = n - i
        ax.broken_barh([(0, bar["barLength"])], (y - 0.35, 0.7), facecolors="#f1f5f9", edgecolors="#94a3b8")
        x = 0
        small_pieces = []
        for pi, piece in enumerate(bar["pieces"]):
            ax.broken_barh([(x, piece["length"])], (y - 0.3, 0.6), facecolors=COLORS[pi % len(COLORS)], edgecolors="white")
            # Wide enough for "ID + length" on two lines; narrower pieces
            # still get just the ID; too narrow for either gets listed in
            # the "Small pieces" legend below the bar instead of no label
            # at all — a bar with lots of small cuts was showing no length
            # for most of them.
            if piece["length"] > bar["barLength"] * 0.08:
                label, size = f"{piece['originalId']}\n{piece['length']:.0f}mm", 7.5
            elif piece["length"] > bar["barLength"] * 0.045:
                label, size = piece["originalId"], 8
            else:
                label = None
                small_pieces.append(piece)
            if label:
                ax.text(x + piece["length"] / 2, y, label, ha="center", va="center",
                         color="white", fontsize=size, fontweight="bold", linespacing=1.4)
            x += piece["length"]
        used = sum(p["length"] for p in bar["pieces"])
        ax.text(bar["barLength"] * 1.01, y, f"Bar {start_index + i + 1} · {used:.0f}/{bar['barLength']:.0f}mm", va="center", fontsize=8, color="#475569")

        if small_pieces:
            counts: dict[tuple[str, float], int] = {}
            for p in small_pieces:
                key = (p["originalId"], p["length"])
                counts[key] = counts.get(key, 0) + 1
            parts = [
                f"{pid} {length:.0f}mm" + (f"×{count}" if count > 1 else "")
                for (pid, length), count in counts.items()
            ]
            ax.text(0, y - 0.46, "Small pieces: " + ", ".join(parts),
                     fontsize=6.5, color="#334155", va="top", ha="left")

    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.set_yticks([])
    ax.set_xlabel("Length (mm)", color="#64748b")
    ax.set_xlim(0, max(b["barLength"] for b in bars) * 1.25)


def _build_cutting_plan_figure(material: dict, cutting_plan: list[dict], kerf: float, title: bool = False):
    """The on-screen chart: one figure, auto-sized to fit every bar (fine
    for scrolling in a browser, not for printing — see the PDF builder
    below for that)."""
    fig, ax = plt.subplots(figsize=(10, 0.72 * len(cutting_plan) + (1.3 if title else 1)))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    _draw_cutting_bars(ax, cutting_plan)
    if title:
        grade = f" · {material['materialGrade']}" if material.get("materialGrade") else ""
        ax.set_title(
            f"{material['name']} ({material['type']}{grade})\nStd: {material['standardLength']:.0f}mm · Kerf: {kerf}mm",
            fontsize=12, fontweight="bold",
        )
    fig.tight_layout()
    return fig


def _build_cutting_plan_cover_page(project_name: str, project_date: str, engineer: str, material_count: int, bar_count: int):
    """Title page: project name + report metadata, same A3-landscape size
    as the material pages that follow it."""
    fig, ax = plt.subplots(figsize=(PDF_PAGE_W, PDF_PAGE_H))
    fig.patch.set_facecolor("#ffffff")
    ax.axis("off")

    ax.text(0.5, 0.72, "CUTTING PLAN", ha="center", fontsize=30, fontweight="bold", color="#1e293b", transform=ax.transAxes)
    ax.text(0.5, 0.60, project_name or "Untitled Project", ha="center", fontsize=22, color="#2563eb", transform=ax.transAxes)

    detail_lines = []
    if project_date:
        detail_lines.append(f"Date: {project_date}")
    if engineer:
        detail_lines.append(f"Engineer: {engineer}")
    detail_lines.append(f"{material_count} material(s) · {bar_count} bar(s) total")
    detail_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    ax.text(0.5, 0.47, "\n".join(detail_lines), ha="center", va="top", fontsize=12, color="#475569", transform=ax.transAxes)

    fig.tight_layout()
    return fig


def _build_cutting_plan_pdf_pages(material: dict, cutting_plan: list[dict], kerf: float, project_name: str = "") -> list:
    """One or more fixed-size (A3 landscape) pages for a material's cutting
    plan — splits onto multiple pages if there are more bars than fit
    legibly on one printed sheet."""
    bars_per_page = max(1, int((PDF_PAGE_H - PDF_HEADER_H - PDF_FOOTER_H) / PDF_BAR_ROW_H))
    total_pages = max(1, -(-len(cutting_plan) // bars_per_page))  # ceil division
    grade = f" · {material['materialGrade']}" if material.get("materialGrade") else ""

    figures = []
    for page in range(total_pages):
        start = page * bars_per_page
        page_bars = cutting_plan[start:start + bars_per_page]
        fig, ax = plt.subplots(figsize=(PDF_PAGE_W, PDF_PAGE_H))
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")
        _draw_cutting_bars(ax, page_bars, start_index=start)
        page_note = f" — page {page + 1} of {total_pages}" if total_pages > 1 else ""
        ax.set_title(
            f"{material['name']} ({material['type']}{grade}){page_note}\nStd: {material['standardLength']:.0f}mm · Kerf: {kerf}mm",
            fontsize=13, fontweight="bold",
        )
        if project_name:
            fig.text(0.01, 0.01, project_name, fontsize=8, color="#94a3b8")
        fig.tight_layout(rect=(0, 0.02, 1, 1))
        figures.append(fig)
    return figures


def render_visualization_tab():
    mats = st.session_state.materials
    if not mats:
        st.info("Add a material and some pieces first.")
        return

    material = _material_by_id(st.session_state.selected_material_id) or mats[0]
    if not material.get("pieces"):
        st.info(f"No cutting pieces defined for {material['name']} yet.")
        return

    cutting_plan = cached_material_metrics(material, st.session_state.kerf)["cuttingPlan"]
    if not cutting_plan:
        st.info("No cutting plan to show.")
        return

    st.markdown(f"#### 📊 {material['name']}")
    st.caption(f"Standard length: {material['standardLength']:.0f}mm · Kerf: {st.session_state.kerf}mm")

    fig = _build_cutting_plan_figure(material, cutting_plan, st.session_state.kerf)
    with st.container(border=True):
        st.pyplot(fig)


# ── Overview tab ─────────────────────────────────────────────────────────────

def render_overview_tab():
    st.markdown("#### 🏠 Project Overview")

    info_bits = []
    if st.session_state.project_date:
        info_bits.append(f"📅 {st.session_state.project_date}")
    if st.session_state.project_engineer:
        info_bits.append(f"👷 {st.session_state.project_engineer}")
    info_bits.append(f"✂️ Kerf: {st.session_state.kerf:.1f}mm")
    st.caption(" · ".join(info_bits))

    mats = st.session_state.materials
    if not mats:
        st.info("No materials yet — head to **🧱 Materials & Pieces** to add your first one.")
        return

    totals = engine.project_totals(mats, st.session_state.kerf)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Materials", len(mats))
    c2.metric("Total Pieces", totals["totalPieces"])
    c3.metric("Total Length (mm)", f"{totals['totalLength']:.0f}")
    c4.metric("Total Weight (kg)", f"{totals['totalWeight']:.0f}")
    c5.metric("Overall Surplus", f"{totals['overallSurplus']:.1f}%")

    col_chart, col_table = st.columns([1, 1.4])

    with col_chart:
        st.markdown("**Material Usage**")
        used = totals["totalLength"]
        waste = max(0.0, totals["totalBought"] - totals["totalLength"])
        with st.container(border=True):
            if totals["totalBought"] > 0:
                fig, ax = plt.subplots(figsize=(4.2, 4.2))
                fig.patch.set_facecolor("#ffffff")
                ax.pie(
                    [used, waste], labels=["Used", "Waste"], colors=["#10b981", "#f59e0b"],
                    autopct="%1.1f%%", startangle=90, pctdistance=0.8,
                    wedgeprops={"width": 0.4, "edgecolor": "white"}, textprops={"fontsize": 10},
                )
                ax.set_aspect("equal")
                fig.tight_layout()
                st.pyplot(fig)
            else:
                st.info("No purchased length yet — add stock quantities or pieces to see usage.")

    with col_table:
        st.markdown("**Materials at a Glance**")
        rows = []
        for m in mats:
            metrics = cached_material_metrics(m, st.session_state.kerf)
            rows.append({
                "Material": m["name"], "Bars": metrics["requiredBars"],
                "Balance": metrics["balance"], "Efficiency (%)": round(metrics["efficiency"], 1),
            })
        with st.container(border=True):
            st.dataframe(
                pd.DataFrame(rows), use_container_width=True, hide_index=True,
                column_config={
                    "Balance": st.column_config.NumberColumn(format="%+d"),
                    "Efficiency (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                },
            )
        st.caption("See **📋 MTO Summary** for the full material take-off table.")


# ── MTO / dashboard tab ──────────────────────────────────────────────────────

def render_mto_tab():
    mats = st.session_state.materials
    if not mats:
        st.info("No materials defined yet.")
        return

    st.markdown("#### 📋 Material Take-Off")
    rows = []
    for m in mats:
        metrics = cached_material_metrics(m, st.session_state.kerf)
        rows.append({
            "Material": m["name"], "Type": m["type"], "Bars Required": metrics["requiredBars"],
            "Standard Length (mm)": m["standardLength"], "Stock Qty": metrics["totalStockQty"],
            "Balance": metrics["balance"], "Total Length (mm)": round(metrics["totalLength"]),
            "Weight (kg)": round(metrics["totalWeight"], 1), "Surplus (%)": round(metrics["surplusPct"], 1),
        })
    with st.container(border=True):
        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True,
            column_config={
                "Balance": st.column_config.NumberColumn(format="%+d"),
                "Surplus (%)": st.column_config.ProgressColumn(min_value=0, max_value=50, format="%.1f%%"),
            },
        )


# ── Export tab ───────────────────────────────────────────────────────────────

def render_export_tab():
    st.markdown("#### 📤 Export")
    mats = st.session_state.materials
    if not mats:
        st.info("No materials to export yet.")
        return

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_rows = []
        for m in mats:
            metrics = cached_material_metrics(m, st.session_state.kerf)
            summary_rows.append({
                "Material Name": m["name"], "Type": m["type"], "Material Grade": m.get("materialGrade", ""),
                "Standard Length (mm)": m["standardLength"], "Weight per Meter (kg/m)": m["weightPerMeter"],
                "Unit Price ($)": m.get("unitPrice", 0), "Required Bars": metrics["requiredBars"],
                "Total Length (mm)": round(metrics["totalLength"]), "Total Weight (kg)": round(metrics["totalWeight"], 1),
                "Total Cost ($)": round(metrics["requiredBars"] * m.get("unitPrice", 0), 2),
                "Efficiency (%)": round(metrics["efficiency"], 1),
            })
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Materials Summary", index=False)

        for m in mats:
            if not m.get("pieces"):
                continue
            piece_rows = [{
                "Piece ID": p["id"], "Material Name": m["name"], "Type": m["type"],
                "Material Grade": m.get("materialGrade", ""), "Length (mm)": p["length"],
                "Quantity": p["quantity"], "Total Length (mm)": p["length"] * p["quantity"],
                "Weight (kg)": round(p["length"] * p["quantity"] / 1000 * m["weightPerMeter"], 1),
                "Notes": p.get("notes", ""),
            } for p in m["pieces"]]
            sheet_name = f"{m['name'][:24]} Pieces"  # Excel sheet names cap at 31 chars
            pd.DataFrame(piece_rows).to_excel(writer, sheet_name=sheet_name, index=False)

            # Bar-by-bar cutting sequence — the actual optimizer output shown
            # in the Cutting Plan tab, previously missing from this export.
            kerf = st.session_state.kerf
            cutting_plan = cached_material_metrics(m, kerf)["cuttingPlan"]
            if cutting_plan:
                plan_rows = []
                for idx, bar in enumerate(cutting_plan):
                    used = sum(p["length"] for p in bar["pieces"])
                    kerf_used = len(bar["pieces"]) * kerf
                    waste = max(0.0, bar["barLength"] - used - kerf_used)
                    efficiency = (used + kerf_used) / bar["barLength"] * 100 if bar["barLength"] else 0
                    plan_rows.append({
                        "Bar Number": idx + 1, "Bar Length (mm)": bar["barLength"],
                        "Used (mm)": round(used), "Kerf (mm)": round(kerf_used),
                        "Waste (mm)": round(waste), "Efficiency (%)": round(efficiency, 1),
                        "Pieces": ", ".join(f"{p['originalId']}({p['length']:.0f}mm)" for p in bar["pieces"]),
                        "Cut Sequence": " | ".join(f"{i + 1}. {p['originalId']} - {p['length']:.0f}mm" for i, p in enumerate(bar["pieces"])),
                    })
                plan_sheet_name = f"{m['name'][:22]} Cut Plan"
                pd.DataFrame(plan_rows).to_excel(writer, sheet_name=plan_sheet_name, index=False)

    st.download_button(
        "⬇️ Download Excel Workbook",
        data=buf.getvalue(),
        file_name=f"{st.session_state.current_project_name.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    materials_with_plans = [m for m in mats if m.get("pieces")]
    if materials_with_plans:
        kerf = st.session_state.kerf
        project_name = st.session_state.current_project_name
        plans = [
            (m, cached_material_metrics(m, kerf)["cuttingPlan"])
            for m in materials_with_plans
        ]
        plans = [(m, cp) for m, cp in plans if cp]

        pdf_buf = BytesIO()
        with PdfPages(pdf_buf) as pdf:
            cover = _build_cutting_plan_cover_page(
                project_name, st.session_state.project_date, st.session_state.project_engineer,
                material_count=len(plans), bar_count=sum(len(cp) for _, cp in plans),
            )
            pdf.savefig(cover)
            plt.close(cover)

            for m, cutting_plan in plans:
                for fig in _build_cutting_plan_pdf_pages(m, cutting_plan, kerf, project_name=project_name):
                    pdf.savefig(fig)
                    plt.close(fig)
        st.download_button(
            "⬇️ Download Cutting Plan PDF",
            data=pdf_buf.getvalue(),
            file_name=f"{st.session_state.current_project_name.replace(' ', '_')}_Cutting_Plan.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ── Admin tab (visible only to supa.ADMIN_EMAIL, mirrors web/script.js) ─────

def _status_for(profile: dict, plan_row: dict | None, now: datetime) -> tuple[str, str]:
    """Return (badge_color, status_text) for one user row."""
    if plan_row:
        end = datetime.fromisoformat(plan_row["end_date"].replace("Z", "+00:00"))
        days_left = (end - now).days
        if days_left > 0:
            return "🟢", f"{plan_row['plan']} · {days_left} day(s) left"
        return "🔴", f"Expired ({plan_row['plan']})"

    created = datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00"))
    trial_end = created + timedelta(days=supa.TRIAL_DAYS)
    days_left = (trial_end - now).days
    if days_left > 0:
        return "🟡", f"Trial · {days_left} day(s) left"
    return "🔴", "Trial Expired"


def render_admin_tab():
    st.markdown("#### 🛡️ Admin — User Access")

    try:
        profiles = supa.cached_list_all_profiles()
        plans = supa.cached_list_all_user_plans()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load users: {exc}")
        return

    if not profiles:
        st.info("No registered users yet.")
        return

    plan_map = {p["user_id"]: p for p in plans}
    now = datetime.now(timezone.utc)

    rows = []
    for p in profiles:
        badge, status = _status_for(p, plan_map.get(p["user_id"]), now)
        rows.append({"": badge, "Email": p["email"], "Status": status, "user_id": p["user_id"]})

    st.dataframe(
        pd.DataFrame(rows), use_container_width=True, hide_index=True,
        column_order=["", "Email", "Status"],
    )

    st.markdown("**Manage access**")
    emails = [r["Email"] for r in rows]
    uids = [r["user_id"] for r in rows]
    idx = st.selectbox("User", options=range(len(emails)), format_func=lambda i: emails[i], key="admin_user_select")
    target_uid = uids[idx]
    target_email = emails[idx]

    c1, c2, c3 = st.columns(3)
    if c1.button("➕ Grant 1 Month", use_container_width=True):
        end_date = datetime.now(timezone.utc) + relativedelta(months=1)
        supa.admin_set_plan(target_uid, "monthly", end_date.isoformat())
        st.toast(f"Granted 1 month to {target_email}", icon="✅")
        st.rerun()
    if c2.button("➕ Grant 1 Year", use_container_width=True):
        end_date = datetime.now(timezone.utc) + relativedelta(years=1)
        supa.admin_set_plan(target_uid, "yearly", end_date.isoformat())
        st.toast(f"Granted 1 year to {target_email}", icon="✅")
        st.rerun()
    if c3.button("🚫 Revoke Access", use_container_width=True):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        supa.admin_set_plan(target_uid, "revoked", yesterday.isoformat())
        st.toast(f"Revoked access for {target_email}", icon="⚠️")
        st.rerun()

    with st.expander("Set a custom expiry date"):
        custom_date = st.date_input("Access expires on", value=datetime.now(timezone.utc) + timedelta(days=30))
        custom_plan = st.selectbox("Plan label", ["monthly", "yearly", "custom"], key="admin_custom_plan")
        if st.button("Apply custom date"):
            end_date = datetime.combine(custom_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=23, minutes=59)
            supa.admin_set_plan(target_uid, custom_plan, end_date.isoformat())
            st.toast(f"Set {target_email} to {custom_plan} until {custom_date}", icon="✅")
            st.rerun()

    st.caption(f"{len(profiles)} registered user(s) total.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    user = st.session_state.get("sb_user")
    if user is None:
        render_login()
        return

    render_sidebar(user)

    theme.banner(
        st.session_state.current_project_name or "Cutting Plan & MTO",
        "Linear cutting optimization & material take-off",
    )
    tab_names = [TAB_OVERVIEW, TAB_MATERIALS, TAB_VISUALIZATION, TAB_MTO, TAB_EXPORT]
    is_admin = user.email == supa.ADMIN_EMAIL
    if is_admin:
        tab_names.append(TAB_ADMIN)

    if st.session_state.get("active_tab") not in tab_names:
        st.session_state.active_tab = tab_names[0]

    # A segmented control (rather than st.tabs) so only the selected
    # section's code actually runs each rerun — st.tabs executes every
    # tab's body on every rerun regardless of which one is visible, which
    # made editing anything re-run the cutting optimizer for every material.
    choice = st.segmented_control(
        "Section", tab_names, default=st.session_state.active_tab, label_visibility="collapsed",
        key="tab_nav",
    )
    if choice is not None:
        st.session_state.active_tab = choice
    active = st.session_state.active_tab

    # Materials & Pieces always runs — its data_editor widgets are the only
    # place pending edits get written into st.session_state.materials, and
    # that write only happens when this function actually executes. With
    # the other sections gated to "only run when active" (for performance),
    # switching away right after an edit — before its own on-change rerun
    # had a chance to run render_materials_tab() — could leave Export/MTO
    # reading pieces data that didn't yet include the last edit. Running
    # this one unconditionally (it's cheap — no optimizer/matplotlib calls)
    # guarantees every other tab sees fully-synced data. It's just hidden
    # via CSS, not skipped, when another section is selected.
    with st.container(key="materials_section"):
        render_materials_tab()
    if active != TAB_MATERIALS:
        st.markdown(
            '<style>div[class*="st-key-materials_section"] { display: none; }</style>',
            unsafe_allow_html=True,
        )

    if active == TAB_OVERVIEW:
        render_overview_tab()
    elif active == TAB_VISUALIZATION:
        render_visualization_tab()
    elif active == TAB_MTO:
        render_mto_tab()
    elif active == TAB_EXPORT:
        render_export_tab()
    elif is_admin and active == TAB_ADMIN:
        render_admin_tab()


if __name__ == "__main__":
    main()
