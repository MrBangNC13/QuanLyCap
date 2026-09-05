import streamlit as st
import pandas as pd
import networkx as nx
import folium
import json
from streamlit_folium import st_folium
import json
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from streamlit_folium import st_folium

# --- KHAI BÁO HÀM DƯỚI ĐÂY (TRƯỚC DÒNG CALL NÓ) ---
def parse_json_data(data):
    G = nx.Graph()
    node_coords = {}

    # Chuyển đổi dữ liệu nếu đầu vào là chuỗi / bytes
    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    # 1. Trường hợp JSON dạng Nodes / Links
    if isinstance(data, dict) and ("nodes" in data or "links" in data):
        for node in data.get("nodes", []):
            node_id = str(node.get("id") or node.get("name")).strip()
            lat = node.get("lat") or node.get("latitude")
            lon = node.get("lng") or node.get("lon") or node.get("longitude")
            if lat is not None and lon is not None:
                node_coords[node_id] = (float(lat), float(lon))
                G.add_node(node_id)

        for link in data.get("links", []) or data.get("edges", []):
            u = str(link.get("from") or link.get("source")).strip()
            v = str(link.get("to") or link.get("target")).strip()
            cable_id = str(link.get("cable_name") or link.get("cable") or f"{u}-{v}").strip()
            length = float(link.get("length", 0.0))
            G.add_edge(u, v, cable=cable_id, length=length)

    # 2. Trường hợp JSON dạng GeoJSON
    elif isinstance(data, dict) and data.get("type") == "FeatureCollection":
        for feature in data.get("features", []):
            geom_type = feature.get("geometry", {}).get("type")
            coords = feature.get("geometry", {}).get("coordinates")
            props = feature.get("properties", {})

            if geom_type == "Point":
                node_id = str(props.get("name") or props.get("id")).strip()
                lon, lat = coords[0], coords[1]
                node_coords[node_id] = (float(lat), float(lon))
                G.add_node(node_id)

            elif geom_type == "LineString":
                u = str(props.get("from")).strip()
                v = str(props.get("to")).strip()
                cable_id = str(props.get("cable_name") or props.get("name") or f"{u}-{v}").strip()
                length = float(props.get("length", 0.0))
                G.add_edge(u, v, cable=cable_id, length=length)

    # 3. Trường hợp JSON dạng danh sách (List of objects)
    elif isinstance(data, list):
        for item in data:
            u = str(item.get("Điểm KN1") or item.get("from") or item.get("source")).strip()
            v = str(item.get("Điểm KN2") or item.get("to") or item.get("target")).strip()
            cable_id = str(item.get("Tên đoạn cáp") or item.get("cable_name") or f"{u}-{v}").strip()
            length = float(item.get("Chiều dài thực (m)") or item.get("length", 0.0))

            lat1 = item.get("lat1") or item.get("lat_1")
            lon1 = item.get("lng1") or item.get("lon_1")
            lat2 = item.get("lat2") or item.get("lat_2")
            lon2 = item.get("lng2") or item.get("lon_2")

            if lat1 and lon1:
                node_coords[u] = (float(lat1), float(lon1))
            if lat2 and lon2:
                node_coords[v] = (float(lat2), float(lon2))

            if u and v:
                G.add_edge(u, v, cable=cable_id, length=length)

    return G, node_coords
# 1. Cấu hình trang
st.set_page_config(page_title="Xác Định Vị Trí Đứt Cáp", layout="wide", initial_sidebar_state="expanded")

# Session state lưu trữ kết quả
if "break_result" not in st.session_state:
    st.session_state.break_result = None
if "break_gps" not in st.session_state:
    st.session_state.break_gps = None

st.title("⚡ XÁC ĐỊNH VỊ TRÍ ĐỨT CÁP")
st.caption("Fiber Optic Break Location Finder")

# 2. Sidebar Lọc & Nhập Dữ Liệu
st.sidebar.title("📂 QUẢN LÝ DỮ LIỆU")

# Cho phép chọn định dạng File đầu vào
data_source = st.sidebar.radio("Chọn định dạng dữ liệu:", ["File Excel (.xlsx)", "File JSON (.json)"])

G = nx.Graph()
node_coords = {}

if data_source == "File Excel (.xlsx)":
    uploaded_file = st.sidebar.file_uploader("Tải lên file Excel", type=["xlsx", "xls"], key="excel_uploader")
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.columns = [str(col).strip() for col in df.columns]
        
        lat_col1 = next((c for c in df.columns if 'lat' in c.lower() and '1' in c.lower()), None)
        lon_col1 = next((c for c in df.columns if 'lng' in c.lower() or ('lon' in c.lower() and '1' in c.lower())), None)
        lat_col2 = next((c for c in df.columns if 'lat' in c.lower() and '2' in c.lower()), None)
        lon_col2 = next((c for c in df.columns if 'lng' in c.lower() or ('lon' in c.lower() and '2' in c.lower())), None)

        if not lat_col1:
            lat_col1 = next((c for c in df.columns if 'lat' in c.lower() or 'vĩ độ' in c.lower()), None)
            lon_col1 = next((c for c in df.columns if 'lng' in c.lower() or 'lon' in c.lower() or 'kinh độ' in c.lower()), None)

        df['POP'] = df['Tên đoạn cáp'].apply(lambda x: str(x).split('.')[0] if '.' in str(x) else str(x))
        selected_pop = st.sidebar.selectbox("LỌC DỮ LIỆU POP", sorted(df['POP'].unique()), key="selected_pop")
        pop_df = df[df['POP'] == selected_pop].copy()

        for _, row in pop_df.iterrows():
            k1 = str(row['Điểm KN1']).strip()
            k2 = str(row['Điểm KN2']).strip()
            cable = str(row['Tên đoạn cáp']).strip()
            length = float(row['Chiều dài thực (m)']) if pd.notnull(row['Chiều dài thực (m)']) else 0.0
            
            try:
                if lat_col1 and lon_col1 and pd.notnull(row[lat_col1]) and pd.notnull(row[lon_col1]):
                    node_coords[k1] = (float(row[lat_col1]), float(row[lon_col1]))
                if lat_col2 and lon_col2 and pd.notnull(row[lat_col2]) and pd.notnull(row[lon_col2]):
                    node_coords[k2] = (float(row[lat_col2]), float(row[lon_col2]))
            except Exception:
                pass

            G.add_edge(k1, k2, cable=cable, length=length)

else:
    # Đọc File JSON
    uploaded_file = st.sidebar.file_uploader("Tải lên file JSON", type=["json"], key="json_uploader")
    if uploaded_file:
        json_data = json.load(uploaded_file)
        
        # Gọi hàm bóc tách dữ liệu JSON
        # (Nếu hàm parse_json_data đã định nghĩa ở trên)
        G, node_coords = parse_json_data(json_data)

# 3. Tính toán và Hiển thị
if len(G.nodes()) > 0:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📍 THÔNG TIN ĐO (OTDR)")
    
    all_nodes = sorted(list(G.nodes()))
    start_node = st.sidebar.selectbox("Điểm đo (Đang đứng)", all_nodes, key="start_node")
    
    neighbors = list(G.neighbors(start_node)) if start_node in G else []
    direction_node = st.sidebar.selectbox("Hướng đo (Xuôi ngọn / Về ODF)", neighbors, key="direction_node")
    
    measured_len = st.sidebar.number_input("Chiều dài đo được (Mét)", min_value=0.0, value=170.0, step=10.0, key="measured_len")

    if st.sidebar.button("🎯 Xác định vị trí đứt", key="btn_calc"):
        if start_node and direction_node:
            current = start_node
            nxt = direction_node
            accumulated = 0.0
            visited = {current}

            b_res = None
            b_gps = None

            while True:
                edge_data = G[current][nxt]
                seg_len = edge_data['length']
                cable_id = edge_data['cable']
                visited.add(nxt)

                if accumulated + seg_len >= measured_len:
                    d1 = measured_len - accumulated
                    d2 = seg_len - d1
                    b_res = {
                        "cable": cable_id,
                        "from": current,
                        "to": nxt,
                        "d1": d1,
                        "d2": d2,
                        "seg_len": seg_len,
                        "total": measured_len
                    }

                    if current in node_coords and nxt in node_coords and seg_len > 0:
                        lat1, lon1 = node_coords[current]
                        lat2, lon2 = node_coords[nxt]
                        ratio = d1 / seg_len
                        break_lat = lat1 + (lat2 - lat1) * ratio
                        break_lon = lon1 + (lon2 - lon1) * ratio
                        b_gps = (break_lat, break_lon)
                    break
                else:
                    accumulated += seg_len
                    next_nodes = [n for n in G.neighbors(nxt) if n not in visited]
                    if not next_nodes:
                        break
                    current = nxt
                    nxt = next_nodes[0]

            st.session_state.break_result = b_res
            st.session_state.break_gps = b_gps

    if st.session_state.break_result:
        res = st.session_state.break_result
        st.sidebar.error("📍 VỊ TRÍ ĐỨT CÁP")
        st.sidebar.markdown(f"**Đoạn cáp:** `{res['cable']}`")
        st.sidebar.markdown(f"• Cách **{res['from']}**: `{res['d1']:.1f}m` / {res['seg_len']}m")
        st.sidebar.markdown(f"• Cách **{res['to']}**: `{res['d2']:.1f}m`")
        
        if st.session_state.break_gps:
            gps = st.session_state.break_gps
            gmap_url = f"https://www.google.com/maps?q={gps[0]},{gps[1]}"
            st.sidebar.markdown(f"📍 **GPS:** `{gps[0]:.6f}, {gps[1]:.6f}`")
            st.sidebar.markdown(f"👉 [**Mở trên Google Maps**]({gmap_url})")

    # Bản đồ
    map_center = [21.0285, 105.8542]
    zoom_lvl = 12

    if st.session_state.break_gps:
        map_center = st.session_state.break_gps
        zoom_lvl = 17
    elif len(node_coords) > 0:
        first_coord = list(node_coords.values())[0]
        map_center = [first_coord[0], first_coord[1]]
        zoom_lvl = 15

    m = folium.Map(location=map_center, zoom_start=zoom_lvl, tiles="OpenStreetMap")

    # CHỈ HIỂN THỊ ĐOẠN BỊ ĐỨT
    if st.session_state.break_result:
        u = st.session_state.break_result['from']
        v = st.session_state.break_result['to']

        if u in node_coords and v in node_coords:
            folium.PolyLine(
                locations=[node_coords[u], node_coords[v]],
                color="blue",
                weight=5,
                opacity=0.8,
                tooltip=f"Đoạn cáp: {st.session_state.break_result['cable']}"
            ).add_to(m)

            folium.CircleMarker(
                location=node_coords[u], radius=6, popup=f"Điểm KN: {u}", tooltip=f"Điểm KN: {u}",
                color="blue", fill=True, fill_color="white"
            ).add_to(m)

            folium.CircleMarker(
                location=node_coords[v], radius=6, popup=f"Điểm KN: {v}", tooltip=f"Điểm KN: {v}",
                color="blue", fill=True, fill_color="white"
            ).add_to(m)

        if st.session_state.break_gps:
            folium.Marker(
                location=st.session_state.break_gps,
                popup=f"CẢNH BÁO ĐỨT CÁP: {st.session_state.break_result['cable']}",
                tooltip="Vị trí đứt cáp dự kiến",
                icon=folium.Icon(color="red", icon="warning", prefix="fa")
            ).add_to(m)

    st_folium(m, width=1000, height=650, key="folium_map")

else:
    st.info("👈 Vui lòng tải file Excel hoặc JSON lên để xem dữ liệu.")
