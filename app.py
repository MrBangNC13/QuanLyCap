import streamlit as st
import pandas as pd
import networkx as nx
import folium
from streamlit_folium import st_folium

# 1. Cấu hình trang
st.set_page_config(page_title="Xác Định Vị Trí Đứt Cáp", layout="wide", initial_sidebar_state="expanded")

# Hàm đọc file Excel có Cache để chống tràn bộ nhớ RAM Streamlit Cloud
@st.cache_data
def load_data(file):
    return pd.read_excel(file)

st.title("⚡ XÁC ĐỊNH VỊ TRÍ ĐỨT CÁP")
st.caption("Fiber Optic Break Location Finder")

# 2. Sidebar Lọc & Nhập Dữ Liệu
st.sidebar.title("📂 QUẢN LÝ DỮ LIỆU")
uploaded_file = st.sidebar.file_uploader("Tải lên file Danh-Sách-Đoạn-Cáp.xlsx", type=["xlsx", "xls"])

if uploaded_file:
    # Đọc dữ liệu qua hàm cache
    df = load_data(uploaded_file)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Tìm cột Tọa độ (hỗ trợ nhiều định dạng tên cột)
    lat_col1 = next((c for c in df.columns if 'lat' in c.lower() and '1' in c.lower()), None)
    lon_col1 = next((c for c in df.columns if 'lng' in c.lower() or 'lon' in c.lower() and '1' in c.lower()), None)
    lat_col2 = next((c for c in df.columns if 'lat' in c.lower() and '2' in c.lower()), None)
    lon_col2 = next((c for c in df.columns if 'lng' in c.lower() or 'lon' in c.lower() and '2' in c.lower()), None)

    if not lat_col1:
        lat_col1 = next((c for c in df.columns if 'lat' in c.lower() or 'vĩ độ' in c.lower()), None)
        lon_col1 = next((c for c in df.columns if 'lng' in c.lower() or 'lon' in c.lower() or 'kinh độ' in c.lower()), None)

    # Lọc tuyến cáp
    df['POP'] = df['Tên đoạn cáp'].apply(lambda x: str(x).split('.')[0] if '.' in str(x) else str(x))
    selected_pop = st.sidebar.selectbox("LỌC DỮ LIỆU POP", sorted(df['POP'].unique()))
    
    pop_df = df[df['POP'] == selected_pop].copy()
    
    # Dựng đồ thị kết nối & Lưu tọa độ các Node
    G = nx.Graph()
    node_coords = {}

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

    st.sidebar.markdown("---")
    st.sidebar.subheader("📍 THÔNG TIN ĐO (OTDR)")
    
    all_nodes = sorted(list(G.nodes()))
    start_node = st.sidebar.selectbox("Điểm đo (Đang đứng)", all_nodes)
    
    neighbors = list(G.neighbors(start_node)) if start_node in G else []
    direction_node = st.sidebar.selectbox("Hướng đo (Xuôi ngọn / Về ODF)", neighbors)
    
    measured_len = st.sidebar.number_input("Chiều dài đo được (Mét)", min_value=0.0, value=170.0, step=10.0)

    btn_calc = st.sidebar.button("🎯 Xác định vị trí đứt")

    break_result = None
    break_gps = None

    if btn_calc and start_node and direction_node:
        current = start_node
        nxt = direction_node
        accumulated = 0.0
        visited = {current}

        while True:
            edge_data = G[current][nxt]
            seg_len = edge_data['length']
            cable_id = edge_data['cable']
            visited.add(nxt)

            if accumulated + seg_len >= measured_len:
                d1 = measured_len - accumulated
                d2 = seg_len - d1
                break_result = {
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
                    break_gps = (break_lat, break_lon)
                break
            else:
                accumulated += seg_len
                next_nodes = [n for n in G.neighbors(nxt) if n not in visited]
                if not next_nodes:
                    break
                current = nxt
                nxt = next_nodes[0]

        if break_result:
            st.sidebar.error("📍 VỊ TRÍ ĐỨT CÁP")
            st.sidebar.markdown(f"**Đoạn cáp:** `{break_result['cable']}`")
            st.sidebar.markdown(f"• Cách **{break_result['from']}**: `{break_result['d1']:.1f}m` / {break_result['seg_len']}m")
            st.sidebar.markdown(f"• Cách **{break_result['to']}**: `{break_result['d2']:.1f}m`")
            
            if break_gps:
                gmap_url = f"https://www.google.com/maps?q={break_gps[0]},{break_gps[1]}"
                st.sidebar.markdown(f"📍 **GPS:** `{break_gps[0]:.6f}, {break_gps[1]:.6f}`")
                st.sidebar.markdown(f"👉 [**Mở trên Google Maps**]({gmap_url})")

    # 3. Hiển thị Bản đồ
    map_center = [21.0285, 105.8542]
    zoom_lvl = 12

    if break_gps:
        map_center = break_gps
        zoom_lvl = 17
    elif len(node_coords) > 0:
        first_coord = list(node_coords.values())[0]
        map_center = [first_coord[0], first_coord[1]]
        zoom_lvl = 15

    m = folium.Map(location=map_center, zoom_start=zoom_lvl, tiles="OpenStreetMap")

    for u, v in G.edges():
        if u in node_coords and v in node_coords:
            folium.PolyLine(
                locations=[node_coords[u], node_coords[v]],
                color="blue",
                weight=4,
                opacity=0.7
            ).add_to(m)

    for node_name, coord in node_coords.items():
        folium.CircleMarker(
            location=coord,
            radius=5,
            popup=node_name,
            color="blue",
            fill=True,
            fill_color="white"
        ).add_to(m)

    if break_gps:
        folium.Marker(
            location=break_gps,
            popup=f"CẢNH BÁO ĐỨT CÁP: {break_result['cable']}",
            tooltip="Vị trí đứt cáp dự kiến",
            icon=folium.Icon(color="red", icon="warning", prefix="fa")
        ).add_to(m)

    st_folium(m, width=1000, height=650)

else:
    st.info("👈 Vui lòng mở thanh điều khiển bên trái và tải file Excel lên để xem dữ liệu.")