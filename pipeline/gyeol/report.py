"""data/REPORT_data.md (레이어별 피처 수·면적 합) + 레이어 PNG (눈으로 확인용)."""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from .config import DATA, region, region_dirs  # noqa: E402

FG, BG, LINE, MUTED = "#33322f", "#ecebe6", "#b4b1a9", "#8a8882"


def data_report(region_id: str, ndvi_items: list[str]) -> None:
    dirs = region_dirs(region_id)
    proc = dirs["processed"]
    s = json.loads((proc / "layers_summary.json").read_text())
    cells = gpd.read_parquet(proc / "cells.parquet")
    spaces = gpd.read_parquet(proc / "spaces.parquet")
    img_dir = DATA / "figures" / region_id
    img_dir.mkdir(parents=True, exist_ok=True)
    figs = render_layers(region_id, img_dir)

    reg = region(region_id)
    lines = [f"# 데이터 보고서 — {reg['name']} ({region_id})", "",
             f"좌표계 `{s['crs']}` · 생성 `make data REGION={region_id}`", "",
             "## 레이어 (연구 범위 = 대상 + 버퍼)", "", "| 레이어 | 피처 수 | 면적 합 (km²) | 길이 합 (km) | 합계 |", "| --- | ---: | ---: | ---: | --- |"]
    for k, v in s["layers"].items():
        if v is None:
            lines.append(f"| {k} | 데이터 없음 | | | |")
            continue
        extra = ", ".join(f"{a}={v[a]:,.0f}" for a in ("sum_pop", "sum_jobs") if a in v)
        lines.append(f"| {k} | {v['features']:,} | {v.get('area_m2', 0) / 1e6:,.3f} | {v.get('length_m', 0) / 1e3:,.1f} | {extra} |")
    t = cells[cells.in_target]
    lines += ["", "## 공간 (정의별)", "", "| 정의 | 공간 수 | 면적 합 (ha) |", "| --- | ---: | ---: |"]
    for d in ("green_only", "with_plaza_playground", "with_pops"):
        m = spaces[f"def_{d}"]
        lines.append(f"| {d} | {int(m.sum()):,} | {spaces.loc[m, 'area_m2'].sum() / 1e4:,.1f} |")
    lines += ["", f"출입구를 경계에서 찾지 못해 대표점 최근접 노드로 대신한 공간: {int(spaces.entrance_fallback.sum())}개", "",
              "## 격자", "", f"- H3 셀 {len(cells):,}개 (대상 안 {len(t):,}개)",
              f"- 대상 안 야간 인구 합 {t.pop_night.sum():,.0f}, 일자리 합 {t.pop_day.sum():,.0f}",
              f"- 셀 중심→보행 노드 거리 중앙값 {cells.node_snap_m.median():.1f} m, 최대 {cells.node_snap_m.max():.1f} m", "",
              "## 녹지성 (Sentinel-2 장면)", "", *[f"- `{i}`" for i in ndvi_items], "",
              "## 출처 버전", "", *[f"- {k}: {v}" for k, v in s.get("versions", {}).items()], "",
              "## 다운로드 기록", "", "| 키 | 출처 | 받은 시각 (UTC) |", "| --- | --- | --- |"]
    for k, v in s.get("sources", {}).items():
        lines.append(f"| {k} | {v.get('source', '')} | {v.get('fetched', '')} |")
    lines += ["", "## 레이어 그림", "", *[f"![{f.stem}](figures/{region_id}/{f.name})" for f in figs], ""]
    (DATA / f"REPORT_data{'' if region_id == 'manhattan' else '_' + region_id}.md").write_text("\n".join(lines))


def render_layers(region_id: str, img_dir) -> list:
    proc = region_dirs(region_id)["processed"]
    cls = np.load(proc / "class5m.npy")
    out = []
    # 지상층 분류 (2배 축소해서 그림)
    c = cls[::4, ::4]
    cmap = ListedColormap([BG, "#4d4c48", "#b4b1a9", "#dcdad3", "#8a8882", "#6f6e6a", "#a9a69e"])
    fig, ax = plt.subplots(figsize=(6, 12), dpi=150)
    ax.imshow(c, cmap=cmap, vmin=0, vmax=6, interpolation="nearest")
    ax.set_axis_off()
    ax.set_title("ground classes: 1 open(free) 2 roadway 3 private 4 sidewalk 5 open(cond.) 6 POPS", fontsize=7, color=FG)
    p = img_dir / "ground_classes.png"
    fig.savefig(p, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    out.append(p)

    cells = gpd.read_parquet(proc / "cells.parquet")
    spaces = gpd.read_parquet(proc / "spaces.parquet")
    L = proc / "layers"
    for name, col in (("pop_night", "pop_night"), ("pop_day", "pop_day")):
        v = cells[col] / (cells["land_m2"] / 1e4)
        if not v.notna().any():
            continue   # 데이터 없음
        fig, ax = plt.subplots(figsize=(6, 12), dpi=120)
        cells.assign(v=v).plot(column="v", ax=ax, cmap="Greys", scheme="quantiles", k=6, linewidth=0)
        ax.set_axis_off()
        ax.set_title(f"{name} per ha (quantiles)", fontsize=8, color=FG)
        p = img_dir / f"{name}.png"
        fig.savefig(p, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        out.append(p)
    fig, ax = plt.subplots(figsize=(6, 12), dpi=120)
    tgt = gpd.read_parquet(L / "target.parquet")
    tgt.boundary.plot(ax=ax, color=LINE, linewidth=0.5)
    for kind, color in (("pops", MUTED), ("schoolyard", MUTED)):
        spaces[spaces.kind == kind].plot(ax=ax, color=color, markersize=2)
    spaces[spaces.def_with_plaza_playground & (spaces.kind != "schoolyard")].plot(ax=ax, color=FG, markersize=2)
    ax.set_axis_off()
    ax.set_title("open spaces (dark: with_plaza_playground, grey: schoolyard/POPS)", fontsize=8, color=FG)
    p = img_dir / "open_spaces.png"
    fig.savefig(p, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    out.append(p)
    try:
        from .config import region_dirs as rd
        ndvi = np.load(rd(region_id)["raw"] / "ndvi.npy")[::4, ::4]
        fig, ax = plt.subplots(figsize=(6, 12), dpi=120)
        ax.imshow(np.where(cls[::4, ::4] > 0, ndvi, np.nan), cmap="Greys", vmin=-0.2, vmax=0.8)
        ax.set_axis_off()
        ax.set_title("NDVI on land (Sentinel-2)", fontsize=8, color=FG)
        p = img_dir / "ndvi.png"
        fig.savefig(p, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        out.append(p)
    except FileNotFoundError:
        pass
    return out
