import json
import re
import math
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from streamlit_folium import st_folium

# -----------------------------------------------------------------------------
# 1. HÀM TÍNH KHOẢNG CÁCH GEODESIC (HAVERSINE) - ĐƠN VỊ: MÉT
# -----------------------------------------------------------------------------
def haversine_distance(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371000  # Bán kính Trái Đất (m)

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# -----------------------------------------------------------------------------
# 2. PARSER BÓC TÁCH FILE TQGP001.JSON VÀ TỰ ĐỘNG CHUẨN HOÁ TUYẾN CÁP
# -----------------------------------------------------------------------------
def parse_json_data(data, max_connect_distance_m=1200):
    G = nx.Graph()
    node_coords = {}

    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    # Bóc tách lớp lồng nhau từ API FPT
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if isinstance(data, str):
        try:
            data = json.loads(data.strip())
        except Exception:
            pass
    if isinstance(data, dict) and "Table" in data:
        table_content = data["Table"]
        if isinstance(table_content, str):
            try:
                table_content = json.loads(table_content)
            except Exception:
                pass
        data = table_content
    if isinstance(data, dict) and "responseResult" in data:
        data = data["responseResult"]

    object_list = []
    if isinstance(data, dict):
        object_list = data.get("result", {}).get("objectInfo", []) or data.get("objectInfo", [])
    elif isinstance(data, list):
        object_list = data

    # 1. Trích xuất danh sách Trạm/Tủ/Tập điểm
    for item in object_list:
        if not isinstance(item, dict):
            continue

        node_id = str(item.get("name") or item.get("id") or "").strip()
        lat_lng_str = str(item.get("latLng", "")).strip()

        if lat_lng_str and node_id:
            coords = re.findall(r"[-+]?\d*\.\d+|\d+", lat_lng_str)
            if len(coords) >= 2:
                lat, lng = float(coords[0]), float(coords[1])
                node_coords[node_id] = (lat, lng)
                G.add_node(node_id, **item)

    # 2. Xây dựng tuyến cáp theo thứ tự tự nhiên (tránh nối chéo)
    node_keys = list(node_coords.keys())
    for i in range(len(node_keys) - 1):
        u, v = node_keys[i], node_keys[i+1]
        dist = haversine_distance(node_coords[u], node_coords[v])
        if dist <= max_connect_distance_m:
            G.add_edge(u, v, cable=f"Tuyến {u} - {v}", length=round(dist, 2))

    return G, node_coords

# -----------------------------------------------------------------------------
# 3. THUẬT TOÁN TÌM ĐIỂM ĐỨT OTDR VÀ LIỆT KÊ CÁC ĐOẠN CÁP BỊ ẢNH HƯỞNG
# -----------------------------------------------------------------------------
def locate_otdr_break(G, node_coords, start_node, otdr_dist):
    try:
        lengths, paths = nx.single_source_dijkstra(G, start_node, weight="length")
    except Exception:
        return None, None, []

    affected_segments = []
    break_coords = None
    target_info = None

    for end_node, path in paths.items():
        if len(path) < 2:
            continue
        accumulated = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_len = G[u][v].get("length", 0.0)
            
            if accumulated <= otdr_dist <= (accumulated + edge_len):
                offset = otdr_dist - accumulated
                ratio = offset / edge_len if edge_len > 0 else 0
                
                if u in node_coords and v in node_coords:
                    lat1, lon1 = node_coords[u]
                    lat2, lon2 = node_coords[v]
                    b_lat = lat1 + ratio * (lat2 - lat1)
                    b_lon = lon1 + ratio * (lon2 - lon1)
                    break_coords = (b_lat, b_lon)
                    target_info = {
                        "u": u, 
                        "v": v, 
                        "offset": round(offset, 2), 
                        "edge_len": edge_len,
                        "path": path
                    }
                affected_segments.append({
                    "from": u,
                    "to": v,
                    "length": edge_len,
                    "cable": G[u][v].get("cable", "Tuyến cáp")
                })
                break
            accumulated += edge_len

    return break_coords, target_info, affected_segments


# -----------------------------------------------------------------------------
# 4. MAIN APP - GIAO DIỆN FPT TELECOM "CHECK VỊ TRÍ SỰ CỐ"
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Hệ thống Check vị trí sự cố cáp quang", 
    page_icon="⚡", 
    layout="wide"
)

# Custom CSS cho chuẩn giao diện FPT
st.markdown("""
    <style>
        .fpt-header {
            background-color: #f37021;
            padding: 15px 20px;
            color: white;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .metric-card {
            background-color: #ffffff;
            border-left: 5px solid #f37021;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-radius: 5px;
            margin-bottom: 10px;
        }
        .danger-card {
            background-color: #fff5f5;
            border: 1px solid #feb2b2;
            border-left: 5px solid #e53e3e;
            padding: 15px;
            border-radius: 5px;
            color: #c53030;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="fpt-header">
        <h2 style="margin:0; padding:0;">⚡ HỆ THỐNG XÁC ĐỊNH VỊ TRÍ SỰ CỐ ĐỨT CÁP QUANG</h2>
        <small>FPT Telecom Optical Cable Break Location Finder</small>
    </div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ QUẢN LÝ DỮ LIỆU & CẤU HÌNH")
file_type = st.sidebar.radio("Chọn định dạng file:", ("File JSON (.json)", "File Excel (.xlsx)"))

uploaded_file = None
if file_type == "File JSON (.json)":
    uploaded_file = st.sidebar.file_uploader("Tải lên file JSON (TQGP001.json)", type=["json"])
    max_dist = st.sidebar.slider("Khoảng cách ghép tuyến tối đa (mét):", 200, 3000, 1200, 100)
else:
    uploaded_file = st.sidebar.file_uploader("Tải lên file Excel", type=["xlsx", "xls"])
    max_dist = 1200

# Xử lý khi có file
if uploaded_file is not None:
    try:
        G = nx.Graph()
        node_coords = {}

        if file_type == "File JSON (.json)":
            content = uploaded_file.read()
            raw_data = json.loads(content.decode("utf-8"))
            G, node_coords = parse_json_data(raw_data, max_connect_distance_m=max_dist)
        else:
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                u = str(row.get("Điểm KN1", "")).strip()
                v = str(row.get("Điểm KN2", "")).strip()
                cable = str(row.get("Tên đoạn cáp", f"{u}-{v}")).strip()
                length = float(row.get("Chiều dài thực (m)", 0.0))
                lat1, lon1 = row.get("Lat1"), row.get("Lon1")
                lat2, lon2 = row.get("Lat2"), row.get("Lon2")

                if u and v: G.add_edge(u, v, cable=cable, length=length)
                if lat1 and lon1: node_coords[u] = (float(lat1), float(lon1))
                if lat2 and lon2: node_coords[v] = (float(lat2), float(lon2))

        if len(G.nodes) > 0:
            # Layout 2 Cột: Bên trái Nhập thông số OTDR, Bên phải hiển thị kết quả & Bản đồ
            left_col, right_col = st.columns([1, 2])

            with left_col:
                st.subheader("🎯 Thông số đo OTDR")
                node_list = sorted(list(G.nodes()))
                start_node = st.selectbox("1. Chọn Trạm / Đầu đo OTDR:", node_list)
                otdr_dist = st.number_input("2. Khoảng cách suy hao / đứt cáp (mét):", min_value=0.0, value=350.0, step=10.0)
                
                btn_calc = st.button("🚀 BẮT ĐẦU TÌM VỊ TRÍ", type="primary", use_container_width=True)

                st.markdown("---")
                st.markdown(f"**Tổng số Trạm/Nút:** `{len(G.nodes)}`")
                st.markdown(f"**Tổng số Tuyến cáp:** `{len(G.edges)}`")

            with right_col:
                break_coords, target_info, affected_segments = None, None, []

                if btn_calc and start_node:
                    break_coords, target_info, affected_segments = locate_otdr_break(G, node_coords, start_node, otdr_dist)

                # Hiển thị Card cảnh báo vị trí
                if target_info and break_coords:
                    st.markdown(f"""
                        <div class="danger-card">
                            <h3 style="margin-top:0;">📍 PHÁT HIỆN ĐIỂM SỰ CỐ</h3>
                            <p><b>Trạm phát OTDR:</b> {start_node}</p>
                            <p><b>Đoạn cáp nghi ngờ đứt:</b> Từ <b>{target_info['u']}</b> đến <b>{target_info['v']}</b></p>
                            <p><b>Khoảng cách điểm đứt:</b> Cách <b>{target_info['u']}</b> đúng <b>{target_info['offset']}m</b> (Tổng đoạn: {target_info['edge_len']}m)</p>
                            <p><b>Tọa độ GPS điểm đứt:</b> <code>{break_coords[0]:.6f}, {break_coords[1]:.6f}</code></p>
                        </div>
                    """, unsafe_allow_html=True)
                elif btn_calc:
                    st.warning("⚠️ Khoảng cách đo vượt quá phạm vi các tuyến cáp kết nối từ trạm này.")

                # Render Bản đồ Folium
                if node_coords:
                    avg_lat = sum(lat for lat, lon in node_coords.values()) / len(node_coords)
                    avg_lon = sum(lon for lat, lon in node_coords.values()) / len(node_coords)

                    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)

                    # Vẽ tuyến cáp
                    for u, v, data in G.edges(data=True):
                        if u in node_coords and v in node_coords:
                            folium.PolyLine(
                                locations=[node_coords[u], node_coords[v]],
                                color="#1e88e5",
                                weight=3,
                                opacity=0.7,
                                popup=f"Tuyến: {u} - {v}"
                            ).add_to(m)

                    # Marker Trạm
                    for n_id, coord in node_coords.items():
                        is_start = (n_id == start_node)
                        folium.CircleMarker(
                            location=coord,
                            radius=6 if not is_start else 10,
                            popup=f"Trạm/Nút: {n_id}",
                            tooltip=n_id,
                            color="green" if is_start else "#0d47a1",
                            fill=True,
                            fill_color="green" if is_start else "#0d47a1"
                        ).add_to(m)

                    # Marker Vị trí đứt cáp
                    if break_coords:
                        folium.Marker(
                            location=break_coords,
                            popup=f"🚨 ĐIỂM ĐỨT CÁP!\nCách {target_info['u']}: {target_info['offset']}m",
                            tooltip="🚨 ĐIỂM SỰ CỐ ĐỨT CÁP",
                            icon=folium.Icon(color="red", icon="warning-sign")
                        ).add_to(m)
                        m.location = list(break_coords)
                        m.zoom_start = 16

                    st_folium(m, width="100%", height=500)

    except Exception as e:
        st.error(f"❌ Có lỗi khi đọc dữ liệu: {str(e)}")
else:
    st.info("👉 Vui lòng tải file TQGP001.json hoặc Excel lên ở thanh menu bên trái để bắt đầu.")
